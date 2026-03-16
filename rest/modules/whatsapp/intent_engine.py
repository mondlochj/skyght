def detect_intent(text: str) -> str:
    """Simple keyword-based intent detection for WhatsApp messages."""
    text = text.lower()

    if any(word in text for word in ['reservacion', 'reserva', 'mesa', 'table', 'book', 'reservar']):
        return 'reservation'

    if any(word in text for word in ['habitacion', 'cuarto', 'room', 'hotel', 'noche', 'stay']):
        return 'booking'

    if any(word in text for word in ['servicio', 'reparar', 'instalar', 'plomeria', 'electricista', 'service', 'repair']):
        return 'job'

    return 'general'
