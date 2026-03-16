
let token = '';

async function register() {
  await fetch('/api/auth/register', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      email: email.value,
      password: password.value
    })
  });
  alert('Registered');
}

async function login() {
  const res = await fetch('/api/auth/login', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      email: email.value,
      password: password.value
    })
  });
  const data = await res.json();
  token = data.token;
  loadTeams();
}

async function loadTeams() {
  const res = await fetch('/api/teams', {
    headers:{'Authorization':'Bearer '+token}
  });
  const teams = await res.json();
  teamsDiv.innerHTML = '<h2>Your Teams</h2>' +
    teams.map(t=>'<div>'+t.name+'</div>').join('');
}
