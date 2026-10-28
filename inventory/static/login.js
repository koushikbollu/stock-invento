'use strict';

const form = document.getElementById('login-form');
const username = document.getElementById('username');
const password = document.getElementById('password');
const visibility = document.getElementById('password-toggle');
const submit = document.getElementById('login-submit');
const submitLabel = document.getElementById('login-submit-label');
const errorBox = document.getElementById('login-error');
const statusBox = document.getElementById('login-status');
let pending = false;
let navigating = false;

function setPending(value) {
  pending = value;
  username.disabled = value;
  password.disabled = value;
  visibility.disabled = value;
  submit.disabled = value;
  submit.setAttribute('aria-busy', String(value));
  submitLabel.textContent = value ? 'Signing in…' : 'Sign in';
}
function clearError() {
  errorBox.hidden = true;
  errorBox.textContent = '';
  username.removeAttribute('aria-invalid');
  password.removeAttribute('aria-invalid');
}
function showError(message, invalidCredentials = false) {
  errorBox.textContent = message;
  errorBox.hidden = false;
  if (invalidCredentials) {
    username.setAttribute('aria-invalid', 'true');
    password.setAttribute('aria-invalid', 'true');
  }
  errorBox.focus();
}
async function readJSON(response) {
  try { return await response.json(); }
  catch (_) { throw new Error('The local server returned an unreadable response. Please try again.'); }
}
visibility.addEventListener('click', () => {
  const shown = password.type === 'password';
  password.type = shown ? 'text' : 'password';
  visibility.textContent = shown ? 'Hide' : 'Show';
  visibility.setAttribute('aria-label', shown ? 'Hide password' : 'Show password');
  visibility.setAttribute('aria-pressed', String(shown));
});
username.addEventListener('input', clearError);
password.addEventListener('input', clearError);
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (pending || !form.reportValidity()) return;
  const credentials = { username: username.value.trim(), password: password.value };
  clearError();
  statusBox.textContent = '';
  setPending(true);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const preauth = await fetch('/api/login-session', { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
    const session = await readJSON(preauth);
    if (!preauth.ok || !session.csrf_token) throw new Error('Could not start a sign-in session. Refresh the page and try again.');
    const response = await fetch('/api/login', {
      method: 'POST', credentials: 'same-origin', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-Stockline-Token': session.csrf_token },
      body: JSON.stringify(credentials),
    });
    const result = await readJSON(response);
    if (response.status === 401) {
      showError('The username or password is incorrect. Please try again.', true);
      return;
    }
    if (response.status === 429) {
      const wait = Number(response.headers.get('Retry-After'));
      showError(Number.isFinite(wait) && wait > 0 ? `Too many sign-in attempts. Try again in ${Math.ceil(wait)} seconds.` : 'Too many sign-in attempts. Wait a moment, then try again.');
      return;
    }
    if (!response.ok || result.error) throw new Error(result.error || 'Sign in could not be completed. Please try again.');
    navigating = true;
    statusBox.textContent = 'Signed in. Opening your workspace…';
    window.location.replace('/');
  } catch (error) {
    showError(error.name === 'AbortError' ? 'Sign in took too long. Check that the local server is running, then try again.' : error instanceof TypeError ? 'Could not reach the local server. Check that it is running, then try again.' : error.message);
  } finally {
    clearTimeout(timeout);
    if (!navigating) setPending(false);
  }
});
