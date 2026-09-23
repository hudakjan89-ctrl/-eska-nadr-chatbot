import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from mailer import (
    _deliver_lead_email,
    _extract_email_address,
    _send_via_resend_one,
    audit_email_configuration,
    format_lead_for_email,
    send_lead_email,
)


class TestMailerFormatting(unittest.TestCase):
    def test_format_lead_strips_internal_instructions(self):
        raw = (
            "[KONTAKTNÍ FORMULÁŘ] E-mail: a@b.cz, Jméno: Jan. "
            "Zákazník právě vyplnil formulář. Napiš krátkou odpověď."
        )
        formatted = format_lead_for_email(raw)
        self.assertIn("Typ: Kontaktní formulář", formatted)
        self.assertNotIn("Zákazník právě vyplnil", formatted)

    def test_extract_email_from_display_name(self):
        self.assertEqual(
            _extract_email_address("Bot <obchod@ceskanadrz.cz>"),
            "obchod@ceskanadrz.cz",
        )


class TestResendDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_resend_success_per_recipient(self):
        os.environ["RESEND_API_KEY"] = "re_test_key"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id":"abc"}'

        with patch("mailer._http_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            ok, err = await _send_via_resend_one("Subj", "Body", "obchod@ceskanadrz.cz")
        self.assertTrue(ok)
        self.assertEqual(err, "")
        mock_post.assert_awaited_once()

    async def test_deliver_retries_smtp_when_resend_fails(self):
        os.environ["RESEND_API_KEY"] = "re_test_key"
        os.environ["SMTP_HOST"] = "smtp.example.com"
        os.environ["SMTP_USER"] = "user@example.com"
        os.environ["SMTP_PASS"] = "secret"

        resend_fail = MagicMock()
        resend_fail.status_code = 403
        resend_fail.text = "domain not verified"

        with patch("mailer._http_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = resend_fail
            with patch("mailer._send_smtp_one", new_callable=AsyncMock) as mock_smtp:
                mock_smtp.return_value = (True, "")
                result = await _deliver_lead_email(
                    "Subj",
                    "Body",
                    "[KONTAKTNÍ FORMULÁŘ] test",
                    ["obchod@ceskanadrz.cz"],
                )
        self.assertTrue(result.ok)
        mock_smtp.assert_awaited_once()


class TestSendLeadEmailOutbox(unittest.IsolatedAsyncioTestCase):
    async def test_failed_send_enqueues_outbox(self):
        with patch("mailer._deliver_lead_email", new_callable=AsyncMock) as mock_deliver:
            from mailer import DeliveryResult

            mock_deliver.return_value = DeliveryResult(
                ok=False,
                last_error="HTTP 403: domain not verified",
                failed_to=["obchod@ceskanadrz.cz"],
            )
            with patch("mailer.discord_configured", return_value=False):
                with patch("logger.upsert_lead_email_outbox") as mock_enqueue:
                    ok = await send_lead_email(
                        "[KONTAKTNÍ FORMULÁŘ] E-mail: x@y.cz",
                        [],
                        session_id="sess-123",
                    )
        self.assertFalse(ok)
        mock_enqueue.assert_called_once()


class TestAuditConfiguration(unittest.IsolatedAsyncioTestCase):
    async def test_warns_on_resend_dev_from_address(self):
        with patch("lead_email_config.effective_resend_api_key", return_value="re_test"), patch(
            "lead_email_config.RESEND_FROM_EMAIL", "Test <onboarding@resend.dev>"
        ), patch("mailer.lec.RESEND_FROM_EMAIL", "Test <onboarding@resend.dev>"), patch(
            "mailer._from_email", return_value="Test <onboarding@resend.dev>"
        ), patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": []}
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            warnings = await audit_email_configuration()
        self.assertTrue(any("resend.dev" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
