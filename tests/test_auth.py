import time
import unittest
import urllib.error
from unittest.mock import patch

from app import app, safe_next_url


class LoginTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY='test-only-secret')
        self.client = app.test_client()

    def login(self, token='refresh-test', next_url='/chat'):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['login_csrf']
        return self.client.post('/login', data={
            'refresh_token': token, 'csrf_token': csrf, 'next': next_url,
        })

    def test_gate_and_csrf(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.get('/api/conversations').status_code, 401)
        with patch('app.exchange_refresh_token') as exchange:
            response = self.client.post('/login', data={'refresh_token': 'secret'})
            self.assertIn(b'Form kedaluwarsa', response.data)
            exchange.assert_not_called()

    @patch('app.exchange_refresh_token')
    def test_opening_another_login_page_keeps_existing_form_valid(self, exchange):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            first_csrf = session['login_csrf']
        self.client.get('/login')
        exchange.return_value = {'access_token': 'valid-access', 'expires_in': 3600}
        response = self.client.post('/login', data={
            'csrf_token': first_csrf, 'refresh_token': 'valid-refresh',
        })
        self.assertEqual(response.status_code, 302)
        exchange.assert_called_once_with('valid-refresh')

    @patch('app.exchange_refresh_token')
    def test_login_encrypted_cookie_and_isolation(self, exchange):
        exchange.return_value = {'access_token': 'access-test', 'refresh_token': 'rotated-test', 'expires_in': 3600}
        response = self.login(token='  refresh-test  ')
        exchange.assert_called_once_with('refresh-test')
        self.assertEqual(response.location, '/chat')
        cookie = self.client.get_cookie('session')
        self.assertNotIn('access-test', cookie.value)
        self.assertNotIn('rotated-test', cookie.value)
        self.assertTrue(cookie.http_only)
        self.assertEqual(self.client.get('/chat').status_code, 200)
        self.assertEqual(app.test_client().get('/api/settings').status_code, 401)
        with self.client.session_transaction() as session:
            self.assertEqual(session['refresh_token'], 'rotated-test')
        self.client.get('/logout')
        self.assertEqual(self.client.get('/api/settings').status_code, 401)

    @patch('app.exchange_refresh_token')
    def test_refresh_expired_access_and_rotation(self, exchange):
        with self.client.session_transaction() as session:
            session.update(access_token='expired', refresh_token='old-refresh', expires_at=time.time()-1)
        exchange.return_value = {'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_in': 3600}
        self.assertEqual(self.client.get('/api/settings').status_code, 200)
        exchange.assert_called_once_with('old-refresh')
        with self.client.session_transaction() as session:
            self.assertEqual(session['refresh_token'], 'new-refresh')

    @patch('app.exchange_refresh_token')
    def test_invalid_token_does_not_leak_provider_body(self, exchange):
        exchange.side_effect = urllib.error.HTTPError('https://example.test', 400, 'sensitive-details', {}, None)
        response = self.login()
        self.assertIn(b'Refresh token tidak valid', response.data)
        self.assertNotIn(b'sensitive-details', response.data)
        self.assertEqual(self.client.get('/api/settings').status_code, 401)

    @patch('app.exchange_refresh_token')
    def test_oversized_session_is_rejected(self, exchange):
        exchange.return_value = {'access_token': 'x'*4000, 'expires_in': 3600}
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get('/api/settings').status_code, 401)

    def test_tampered_cookie_and_redirects(self):
        self.client.set_cookie('session', 'tampered-cookie')
        self.assertEqual(self.client.get('/api/settings').status_code, 401)
        for value in ['//evil.test', '/\\evil.test', 'https://evil.test', '/\nevil']:
            self.assertEqual(safe_next_url(value), '/')
        self.assertEqual(safe_next_url('/chat'), '/chat')


if __name__ == '__main__':
    unittest.main()
