
const express = require('express');
const auth = require('../middleware/auth');
const { Pool } = require('pg');
const { v4: uuidv4 } = require('uuid');

const router = express.Router();
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

router.post('/', auth, async (req, res) => {
  const id = uuidv4();
  const { name } = req.body;
  await pool.query(
    'INSERT INTO teams(id,name,owner_id) VALUES($1,$2,$3)',
    [id, name, req.user.id]
  );
  res.json({ message: 'Team created' });
});

router.get('/', auth, async (req, res) => {
  const result = await pool.query(
    'SELECT * FROM teams WHERE owner_id=$1',
    [req.user.id]
  );
  res.json(result.rows);
});

module.exports = router;
