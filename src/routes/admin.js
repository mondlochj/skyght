
const express = require('express');
const auth = require('../middleware/auth');
const { Pool } = require('pg');

const router = express.Router();
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

router.get('/users', auth, async (req, res) => {
  if (req.user.role !== 'admin')
    return res.status(403).json({ message: 'Forbidden' });

  const users = await pool.query('SELECT id,email,role FROM users');
  res.json(users.rows);
});

module.exports = router;
