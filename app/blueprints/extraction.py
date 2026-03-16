from flask import Blueprint, request, jsonify, g, Response
import uuid
import re
import json
import csv
import io
import os
import tempfile
import traceback
from datetime import datetime
from db import get_connection
from auth_utils import login_required

# PDF table extraction
import pdfplumber

extraction_bp = Blueprint('extraction', __name__, url_prefix='/api/extraction')

# ============== Field Type Patterns ==============

PATTERNS = {
    'date': [
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b',  # MM/DD/YYYY, DD-MM-YYYY
        r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',  # YYYY-MM-DD
        r'\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b',  # January 15, 2024
        r'\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b',  # 15 January 2024
    ],
    'currency': [
        r'[\$\£\€]\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # $1,234.56
        r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|EUR|GBP|dollars?)',  # 1234.56 USD
        r'(?:Total|Amount|Price|Cost|Subtotal|Tax|Tip)[\s:]*[\$\£\€]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
    ],
    'email': [
        r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',
    ],
    'phone': [
        r'\b(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b',  # US format
        r'\b(\d{3}[-.\s]\d{3}[-.\s]\d{4})\b',
        r'\b(\(\d{3}\)\s*\d{3}[-.\s]\d{4})\b',
    ],
    'number': [
        r'\b(\d+(?:\.\d+)?)\b',
    ],
    'invoice_number': [
        r'(?:Invoice|Inv|Invoice\s*#|Invoice\s*No\.?|Invoice\s*Number)[\s:#]*([A-Z0-9-]+)',
        r'(?:Order|Order\s*#|Order\s*No\.?)[\s:#]*([A-Z0-9-]+)',
    ],
    'account_number': [
        r'(?:Account|Acct|Account\s*#|Account\s*No\.?)[\s:#]*(\d+)',
    ],
    'percentage': [
        r'(\d+(?:\.\d+)?)\s*%',
    ],
    'url': [
        r'(https?://[^\s]+)',
        r'(www\.[^\s]+)',
    ],
}

# ============== Pre-built Templates ==============

SYSTEM_TEMPLATES = [
    {
        'id': '00000000-0000-0000-0000-000000000001',
        'name': 'Receipt',
        'description': 'Extract data from retail receipts',
        'template_type': 'receipt',
        'is_system': True,
        'fields': [
            {'name': 'vendor_name', 'label': 'Vendor/Store Name', 'type': 'text', 'pattern': r'^(.+?)(?:\n|$)', 'hint': 'Usually at the top'},
            {'name': 'date', 'label': 'Date', 'type': 'date', 'required': True},
            {'name': 'subtotal', 'label': 'Subtotal', 'type': 'currency', 'pattern': r'(?:Subtotal|Sub-total|Sub total)[\s:]*[\$]?(\d+\.\d{2})'},
            {'name': 'tax', 'label': 'Tax', 'type': 'currency', 'pattern': r'(?:Tax|Sales Tax|VAT)[\s:]*[\$]?(\d+\.\d{2})'},
            {'name': 'total', 'label': 'Total', 'type': 'currency', 'pattern': r'(?:Total|Grand Total|Amount Due|Balance Due)[\s:]*[\$]?(\d+\.\d{2})', 'required': True},
            {'name': 'payment_method', 'label': 'Payment Method', 'type': 'text', 'pattern': r'(VISA|MASTERCARD|AMEX|CASH|DEBIT|CREDIT|CARD)'},
            {'name': 'card_last_four', 'label': 'Card Last 4', 'type': 'text', 'pattern': r'(?:CARD|VISA|MC|MASTERCARD|AMEX)[^\d]*(\d{4})'},
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000002',
        'name': 'Invoice',
        'description': 'Extract data from business invoices',
        'template_type': 'invoice',
        'is_system': True,
        'fields': [
            {'name': 'invoice_number', 'label': 'Invoice Number', 'type': 'invoice_number', 'required': True},
            {'name': 'invoice_date', 'label': 'Invoice Date', 'type': 'date', 'pattern': r'(?:Invoice Date|Date|Dated)[\s:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', 'required': True},
            {'name': 'due_date', 'label': 'Due Date', 'type': 'date', 'pattern': r'(?:Due Date|Payment Due|Due)[\s:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'},
            {'name': 'vendor_name', 'label': 'Vendor/Company', 'type': 'text', 'pattern': r'^(.+?)(?:\n|$)'},
            {'name': 'bill_to', 'label': 'Bill To', 'type': 'text', 'pattern': r'(?:Bill To|Billed To|Customer)[\s:]*\n?(.+?)(?:\n|$)'},
            {'name': 'subtotal', 'label': 'Subtotal', 'type': 'currency', 'pattern': r'(?:Subtotal|Sub-total)[\s:]*[\$]?(\d{1,3}(?:,\d{3})*\.\d{2})'},
            {'name': 'tax', 'label': 'Tax', 'type': 'currency', 'pattern': r'(?:Tax|Sales Tax|VAT|GST)[\s:]*[\$]?(\d{1,3}(?:,\d{3})*\.\d{2})'},
            {'name': 'total', 'label': 'Total Amount', 'type': 'currency', 'pattern': r'(?:Total|Grand Total|Amount Due|Balance Due|Total Due)[\s:]*[\$]?(\d{1,3}(?:,\d{3})*\.\d{2})', 'required': True},
            {'name': 'payment_terms', 'label': 'Payment Terms', 'type': 'text', 'pattern': r'(?:Terms|Payment Terms)[\s:]*(.+?)(?:\n|$)'},
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000003',
        'name': 'Business Card',
        'description': 'Extract contact information from business cards',
        'template_type': 'business_card',
        'is_system': True,
        'fields': [
            {'name': 'name', 'label': 'Name', 'type': 'text', 'pattern': r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', 'required': True},
            {'name': 'title', 'label': 'Job Title', 'type': 'text', 'pattern': r'((?:CEO|CTO|CFO|President|Director|Manager|Engineer|Developer|Designer|Consultant|VP|Vice President|Executive|Partner|Associate|Analyst|Specialist)[^\n]*)'},
            {'name': 'company', 'label': 'Company', 'type': 'text'},
            {'name': 'email', 'label': 'Email', 'type': 'email', 'required': True},
            {'name': 'phone', 'label': 'Phone', 'type': 'phone'},
            {'name': 'website', 'label': 'Website', 'type': 'url'},
            {'name': 'address', 'label': 'Address', 'type': 'text', 'pattern': r'(\d+[^,\n]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)[^,\n]*(?:,\s*[^,\n]+){1,3})'},
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000004',
        'name': 'Expense Report',
        'description': 'Extract expense details',
        'template_type': 'expense',
        'is_system': True,
        'fields': [
            {'name': 'date', 'label': 'Date', 'type': 'date', 'required': True},
            {'name': 'vendor', 'label': 'Vendor/Merchant', 'type': 'text'},
            {'name': 'category', 'label': 'Category', 'type': 'text', 'pattern': r'(Travel|Meals|Office|Supplies|Equipment|Transportation|Lodging|Entertainment|Software|Services)'},
            {'name': 'description', 'label': 'Description', 'type': 'text'},
            {'name': 'amount', 'label': 'Amount', 'type': 'currency', 'required': True},
            {'name': 'payment_method', 'label': 'Payment Method', 'type': 'text'},
        ]
    },
]


def extract_field(text, field):
    """Extract a single field from text using patterns."""
    field_type = field.get('type', 'text')
    custom_pattern = field.get('pattern')

    # Try custom pattern first
    if custom_pattern:
        try:
            match = re.search(custom_pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return {
                    'value': match.group(1) if match.groups() else match.group(0),
                    'confidence': 0.9,
                    'raw_match': match.group(0)
                }
        except re.error:
            pass

    # Try type-based patterns
    if field_type in PATTERNS:
        for pattern in PATTERNS[field_type]:
            try:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    return {
                        'value': match.group(1) if match.groups() else match.group(0),
                        'confidence': 0.8,
                        'raw_match': match.group(0)
                    }
            except re.error:
                continue

    return None


def extract_key_value_pairs(text):
    """Extract key:value pairs from text."""
    pairs = {}

    # Pattern for "Key: Value" or "Key - Value" or "Key  Value"
    patterns = [
        r'^([A-Za-z][A-Za-z\s]{1,30}):\s*(.+?)$',
        r'^([A-Za-z][A-Za-z\s]{1,30})\s{2,}(.+?)$',
    ]

    for line in text.split('\n'):
        line = line.strip()
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                key = match.group(1).strip().lower().replace(' ', '_')
                value = match.group(2).strip()
                if value and len(value) < 200:  # Sanity check
                    pairs[key] = value
                break

    return pairs


def extract_line_items(text):
    """Extract table-like line items from text."""
    items = []

    # Look for lines with quantity, description, and price
    # Pattern: quantity  description  price
    item_pattern = r'(\d+)\s+(.+?)\s+[\$]?(\d+\.\d{2})'

    for match in re.finditer(item_pattern, text):
        items.append({
            'quantity': match.group(1),
            'description': match.group(2).strip(),
            'price': match.group(3)
        })

    return items


def run_extraction(text, template):
    """Run extraction on text using a template."""
    fields = template.get('fields', [])
    results = {}

    for field in fields:
        field_name = field['name']
        extracted = extract_field(text, field)

        if extracted:
            results[field_name] = extracted
        elif field.get('required'):
            results[field_name] = {
                'value': None,
                'confidence': 0,
                'error': 'Required field not found'
            }

    # Also extract key-value pairs that might not be in template
    kv_pairs = extract_key_value_pairs(text)
    for key, value in kv_pairs.items():
        if key not in results:
            results[f'detected_{key}'] = {
                'value': value,
                'confidence': 0.6,
                'auto_detected': True
            }

    # Check for line items
    line_items = extract_line_items(text)
    if line_items:
        results['line_items'] = {
            'value': line_items,
            'confidence': 0.7,
            'type': 'table'
        }

    return results


# ============== API Routes ==============

@extraction_bp.route('/templates', methods=['GET'])
@login_required
def list_templates():
    """List all available templates (system + team)."""
    team_id = request.args.get('team_id')

    # Start with system templates
    templates = [dict(t) for t in SYSTEM_TEMPLATES]

    # Add team templates if team_id provided
    if team_id:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT * FROM extraction_templates
            WHERE team_id = %s OR team_id IS NULL
            ORDER BY created_at DESC
        ''', (team_id,))
        custom_templates = cur.fetchall()
        cur.close()
        conn.close()

        templates.extend(custom_templates)

    return jsonify({'templates': templates})


@extraction_bp.route('/templates', methods=['POST'])
@login_required
def create_template():
    """Create a custom extraction template."""
    data = request.get_json()

    name = data.get('name')
    description = data.get('description', '')
    template_type = data.get('template_type', 'custom')
    fields = data.get('fields', [])
    team_id = data.get('team_id')

    if not name or not fields:
        return jsonify({'error': 'Name and fields are required'}), 400

    template_id = str(uuid.uuid4())

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO extraction_templates (id, name, description, template_type, fields, team_id, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (template_id, name, description, template_type, json.dumps(fields), team_id, g.user['id']))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Template created', 'id': template_id})


@extraction_bp.route('/templates/<template_id>', methods=['GET'])
@login_required
def get_template(template_id):
    """Get a specific template."""
    # Check system templates first
    for t in SYSTEM_TEMPLATES:
        if t['id'] == template_id:
            return jsonify(t)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM extraction_templates WHERE id = %s', (template_id,))
    template = cur.fetchone()
    cur.close()
    conn.close()

    if not template:
        return jsonify({'error': 'Template not found'}), 404

    return jsonify(template)


@extraction_bp.route('/templates/<template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    """Delete a custom template."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM extraction_templates WHERE id = %s AND created_by = %s AND is_system = FALSE',
        (template_id, g.user['id'])
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        return jsonify({'error': 'Template not found or cannot be deleted'}), 404

    return jsonify({'message': 'Template deleted'})


@extraction_bp.route('/extract', methods=['POST'])
@login_required
def extract_data():
    """Extract structured data from OCR text using a template."""
    data = request.get_json()

    text = data.get('text', '')
    template_id = data.get('template_id')
    document_id = data.get('document_id')  # Optional, to save extraction

    if not text:
        return jsonify({'error': 'Text is required'}), 400

    # Get template
    template = None
    for t in SYSTEM_TEMPLATES:
        if t['id'] == template_id:
            template = t
            break

    if not template and template_id:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM extraction_templates WHERE id = %s', (template_id,))
        template = cur.fetchone()
        cur.close()
        conn.close()

    if not template:
        # No template - do auto-extraction
        template = {
            'name': 'Auto-detect',
            'fields': [
                {'name': 'dates', 'type': 'date'},
                {'name': 'amounts', 'type': 'currency'},
                {'name': 'emails', 'type': 'email'},
                {'name': 'phones', 'type': 'phone'},
            ]
        }

    # Run extraction
    results = run_extraction(text, template)

    # Save extraction if document_id provided
    extraction_id = None
    if document_id:
        extraction_id = str(uuid.uuid4())
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO extractions (id, document_id, template_id, extracted_fields, raw_text)
            VALUES (%s, %s, %s, %s, %s)
        ''', (extraction_id, document_id, template_id, json.dumps(results), text))
        conn.commit()
        cur.close()
        conn.close()

    return jsonify({
        'extraction_id': extraction_id,
        'template': template.get('name'),
        'fields': results
    })


@extraction_bp.route('/extract/auto', methods=['POST'])
@login_required
def auto_extract():
    """Auto-detect document type and extract data."""
    data = request.get_json()
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'Text is required'}), 400

    text_lower = text.lower()

    # Detect document type based on keywords
    detected_type = 'unknown'
    template = None

    if any(kw in text_lower for kw in ['invoice', 'inv #', 'invoice number', 'bill to']):
        detected_type = 'invoice'
        template = SYSTEM_TEMPLATES[1]
    elif any(kw in text_lower for kw in ['receipt', 'thank you for your purchase', 'change due', 'subtotal']):
        detected_type = 'receipt'
        template = SYSTEM_TEMPLATES[0]
    elif any(kw in text_lower for kw in ['expense', 'reimbursement', 'expense report']):
        detected_type = 'expense'
        template = SYSTEM_TEMPLATES[3]
    elif re.search(r'@.*\.(com|org|net|io)', text_lower) and re.search(r'\d{3}[-.\s]\d{3}[-.\s]\d{4}', text):
        detected_type = 'business_card'
        template = SYSTEM_TEMPLATES[2]

    if template:
        results = run_extraction(text, template)
    else:
        # Generic extraction
        results = {}
        for field_type, patterns in PATTERNS.items():
            matches = []
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group(1) if match.groups() else match.group(0)
                    if value not in matches:
                        matches.append(value)
            if matches:
                results[field_type] = {
                    'value': matches[0] if len(matches) == 1 else matches,
                    'confidence': 0.7
                }

        # Add key-value pairs
        kv_pairs = extract_key_value_pairs(text)
        for key, value in kv_pairs.items():
            results[key] = {'value': value, 'confidence': 0.6}

    return jsonify({
        'detected_type': detected_type,
        'template': template.get('name') if template else 'Auto-detect',
        'fields': results
    })


@extraction_bp.route('/export/json', methods=['POST'])
@login_required
def export_json():
    """Export extracted data as JSON."""
    data = request.get_json()
    extractions = data.get('extractions', [])
    filename = data.get('filename', 'extraction')

    # Handle array of extractions (from frontend) or single fields object
    if extractions and len(extractions) > 0:
        fields = extractions[0].get('fields') or extractions[0].get('extracted_fields', {})
    else:
        fields = data.get('fields', {})

    # Clean up the data for export
    export_data = {}
    for key, value in fields.items():
        if isinstance(value, dict):
            export_data[key] = value.get('value')
        else:
            export_data[key] = value

    response = Response(
        json.dumps(export_data, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}.json'}
    )
    return response


@extraction_bp.route('/export/csv', methods=['POST'])
@login_required
def export_csv():
    """Export extracted data as CSV."""
    data = request.get_json()
    extractions = data.get('extractions', [])
    filename = data.get('filename', 'extraction')

    # Handle array of extractions (from frontend) or single fields object
    if extractions and len(extractions) > 0:
        fields = extractions[0].get('fields') or extractions[0].get('extracted_fields', {})
    else:
        fields = data.get('fields', {})

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    headers = []
    values = []

    for key, value in fields.items():
        if key == 'line_items' and isinstance(value, dict) and value.get('type') == 'table':
            continue  # Handle line items separately
        headers.append(key)
        if isinstance(value, dict):
            values.append(value.get('value', ''))
        else:
            values.append(value)

    writer.writerow(headers)
    writer.writerow(values)

    # Add line items as separate rows if present
    line_items = fields.get('line_items', {})
    if isinstance(line_items, dict) and line_items.get('value'):
        writer.writerow([])  # Blank row
        writer.writerow(['Line Items'])
        writer.writerow(['Quantity', 'Description', 'Price'])
        for item in line_items['value']:
            writer.writerow([item.get('quantity'), item.get('description'), item.get('price')])

    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}.csv'}
    )
    return response


@extraction_bp.route('/extractions/<document_id>', methods=['GET'])
@login_required
def get_extractions(document_id):
    """Get all extractions for a document."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT e.*, et.name as template_name
        FROM extractions e
        LEFT JOIN extraction_templates et ON e.template_id = et.id
        WHERE e.document_id = %s
        ORDER BY e.created_at DESC
    ''', (document_id,))
    extractions = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(extractions)


# ============== Table Extraction ==============

def clean_table_value(val):
    """Clean and normalize table cell values."""
    if val is None:
        return ''
    val = str(val).strip()
    # Remove excessive whitespace
    val = ' '.join(val.split())
    return val


def detect_header_row(table):
    """Detect which row is the header based on common patterns."""
    if not table or len(table) == 0:
        return 0

    header_keywords = [
        'item', 'description', 'qty', 'quantity', 'price', 'amount', 'total',
        'part', 'number', 'sku', 'product', 'unit', 'rate', 'subtotal',
        'service', 'cost', 'ext', 'extended', 'line', 'no', '#', 'date'
    ]

    best_row = 0
    best_score = 0

    for i, row in enumerate(table[:5]):  # Check first 5 rows
        if not row:
            continue
        score = 0
        for cell in row:
            cell_lower = str(cell).lower() if cell else ''
            for keyword in header_keywords:
                if keyword in cell_lower:
                    score += 1
                    break
        if score > best_score:
            best_score = score
            best_row = i

    return best_row if best_score > 0 else 0


def normalize_headers(headers):
    """Normalize header names for consistency."""
    normalized = []
    seen = {}

    for h in headers:
        # Clean the header
        h_clean = clean_table_value(h)
        if not h_clean:
            h_clean = 'column'

        # Convert to snake_case
        h_norm = h_clean.lower()
        h_norm = re.sub(r'[^a-z0-9]+', '_', h_norm)
        h_norm = h_norm.strip('_')

        if not h_norm:
            h_norm = 'column'

        # Handle duplicates
        if h_norm in seen:
            seen[h_norm] += 1
            h_norm = f"{h_norm}_{seen[h_norm]}"
        else:
            seen[h_norm] = 0

        normalized.append({
            'key': h_norm,
            'label': h_clean
        })

    return normalized


def extract_table_from_text(page):
    """Extract table from text layout when no explicit table structure exists."""
    try:
        # Get text with position info
        words = page.extract_words(keep_blank_chars=True, x_tolerance=3, y_tolerance=3)
        if not words:
            return None

        # Group words by their y-position (rows)
        rows_dict = {}
        for word in words:
            # Round y to group words on same line
            y_key = round(word['top'] / 5) * 5
            if y_key not in rows_dict:
                rows_dict[y_key] = []
            rows_dict[y_key].append(word)

        # Sort rows by y position
        sorted_rows = sorted(rows_dict.items(), key=lambda x: x[0])

        if len(sorted_rows) < 2:
            return None

        # Detect column boundaries using word x-positions
        all_x_positions = []
        for _, words_in_row in sorted_rows:
            for word in words_in_row:
                all_x_positions.append(round(word['x0'] / 10) * 10)

        # Find common x-positions (potential column starts)
        from collections import Counter
        x_counts = Counter(all_x_positions)
        common_x = sorted([x for x, count in x_counts.items() if count >= len(sorted_rows) * 0.3])

        if len(common_x) < 2:
            return None

        # Build table rows
        table = []
        for _, words_in_row in sorted_rows:
            row = [''] * len(common_x)
            sorted_words = sorted(words_in_row, key=lambda w: w['x0'])

            for word in sorted_words:
                word_x = round(word['x0'] / 10) * 10
                # Find which column this word belongs to
                col_idx = 0
                for i, col_x in enumerate(common_x):
                    if word_x >= col_x:
                        col_idx = i
                if col_idx < len(row):
                    if row[col_idx]:
                        row[col_idx] += ' ' + word['text']
                    else:
                        row[col_idx] = word['text']

            # Only add rows that have content
            if any(cell.strip() for cell in row):
                table.append(row)

        if len(table) < 2:
            return None

        return table

    except Exception as e:
        print(f"Text-based table extraction failed: {e}")
        return None



    """Extract all tables from a PDF file."""
    tables_data = []

    with pdfplumber.open(pdf_path) as pdf:
        page_numbers = pages if pages else range(len(pdf.pages))

        for page_num in page_numbers:
            if page_num >= len(pdf.pages):
                continue

            page = pdf.pages[page_num]

            # Try standard table extraction first (works for PDFs with table borders)
            tables = page.extract_tables()

            # If no tables found, try with different settings
            if not tables:
                # Try with explicit line finding
                tables = page.extract_tables({
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 5,
                    "join_tolerance": 5,
                })

            # If still no tables, try text-based extraction
            if not tables:
                text_table = extract_table_from_text(page)
                if text_table:
                    tables = [text_table]

            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:  # Need at least header + 1 row
                    continue

                # Detect header row
                header_row_idx = detect_header_row(table)

                # Get headers
                raw_headers = table[header_row_idx]
                headers = normalize_headers(raw_headers)

                # Get data rows
                rows = []
                for row in table[header_row_idx + 1:]:
                    if not row or all(not cell for cell in row):
                        continue  # Skip empty rows

                    row_data = {}
                    for i, cell in enumerate(row):
                        if i < len(headers):
                            row_data[headers[i]['key']] = clean_table_value(cell)

                    # Skip rows that appear to be totals/summaries
                    row_text = ' '.join(str(v) for v in row_data.values()).lower()
                    if any(kw in row_text for kw in ['total', 'subtotal', 'tax', 'grand total', 'balance due']):
                        # Still include but mark as summary
                        row_data['_is_summary'] = True

                    rows.append(row_data)

                if rows:
                    tables_data.append({
                        'page': page_num + 1,
                        'table_index': table_idx,
                        'headers': headers,
                        'rows': rows,
                        'row_count': len(rows)
                    })

    return tables_data


@extraction_bp.route('/tables', methods=['POST'])
@login_required
def extract_tables():
    """Extract tables from an uploaded PDF."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    # Check file type
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are supported for table extraction'}), 400

    # Get optional page numbers
    pages_param = request.form.get('pages')
    pages = None
    if pages_param:
        try:
            pages = [int(p.strip()) - 1 for p in pages_param.split(',')]  # Convert to 0-indexed
        except ValueError:
            pass

    # Save to temp file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    try:
        file.save(temp_path)

        # Extract tables
        tables = extract_tables_from_pdf(temp_path, pages)

        return jsonify({
            'success': True,
            'tables': tables,
            'table_count': len(tables)
        })

    except Exception as e:
        print(f"Table extraction error: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'Table extraction failed: {str(e)}'}), 500
    finally:
        os.close(temp_fd)
        os.unlink(temp_path)


@extraction_bp.route('/tables/from-document/<document_id>', methods=['POST'])
@login_required
def extract_tables_from_document(document_id):
    """Extract tables from a stored document."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM documents WHERE id = %s', (document_id,))
    doc = cur.fetchone()
    cur.close()
    conn.close()

    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    # Check if it's a PDF
    if doc.get('file_type') != 'application/pdf':
        return jsonify({'error': 'Only PDF documents support table extraction'}), 400

    # Get the file path (assuming documents are stored with their ID)
    # You'll need to adjust this based on how files are stored
    file_path = f"/home/administrator/skyght/app/uploads/{document_id}.pdf"

    if not os.path.exists(file_path):
        return jsonify({'error': 'Document file not found'}), 404

    try:
        tables = extract_tables_from_pdf(file_path)
        return jsonify({
            'success': True,
            'document_id': document_id,
            'tables': tables,
            'table_count': len(tables)
        })
    except Exception as e:
        return jsonify({'error': f'Table extraction failed: {str(e)}'}), 500


@extraction_bp.route('/tables/export/csv', methods=['POST'])
@login_required
def export_table_csv():
    """Export extracted table data as CSV."""
    data = request.get_json()
    table = data.get('table', {})
    filename = data.get('filename', 'table_export')

    headers = table.get('headers', [])
    rows = table.get('rows', [])

    if not headers or not rows:
        return jsonify({'error': 'No table data provided'}), 400

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header row (use labels)
    header_labels = [h['label'] for h in headers]
    writer.writerow(header_labels)

    # Write data rows
    header_keys = [h['key'] for h in headers]
    for row in rows:
        if row.get('_is_summary'):
            continue  # Optionally skip summary rows
        row_values = [row.get(key, '') for key in header_keys]
        writer.writerow(row_values)

    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}.csv'}
    )
    return response


@extraction_bp.route('/tables/save', methods=['POST'])
@login_required
def save_table_extraction():
    """Save extracted table to database."""
    data = request.get_json()

    document_id = data.get('document_id')
    table = data.get('table', {})
    table_name = data.get('table_name', 'Extracted Table')

    if not table.get('headers') or not table.get('rows'):
        return jsonify({'error': 'No table data provided'}), 400

    extraction_id = str(uuid.uuid4())

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO extractions (id, document_id, template_id, extracted_fields, raw_text, status)
        VALUES (%s, %s, NULL, %s, %s, 'completed')
    ''', (
        extraction_id,
        document_id,
        json.dumps({
            'type': 'table',
            'name': table_name,
            'headers': table.get('headers'),
            'rows': table.get('rows'),
            'row_count': len(table.get('rows', []))
        }),
        f"Table extraction: {table_name}"
    ))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        'success': True,
        'extraction_id': extraction_id,
        'message': 'Table saved successfully'
    })
