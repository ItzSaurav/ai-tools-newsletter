"""
tests/test_build_draft.py — Tests for build_draft.py SMTP send logic.

Tests mock smtplib.SMTP so no real network calls are made.
Covers:
  - send_review_email logs SMTP response dict (empty = success)
  - send_review_email raises EmailError on SMTPException (NOT silent swallow)
  - "sent successfully" is NOT logged on failure
  - Partial-rejection dict from sendmail() triggers EmailError
  - Missing credentials raise EmailError immediately (not silent skip)
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import smtplib
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from config import EmailError


# ── import function under test ────────────────────────────────────────────────
from build_draft import send_review_email


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_smtp_mock(sendmail_return=None, sendmail_raises=None):
    """Return a mock SMTP server instance."""
    smtp = MagicMock(spec=smtplib.SMTP)
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    smtp.starttls.return_value = (220, b"Ready")
    smtp.login.return_value = (235, b"Accepted")
    smtp.quit.return_value = (221, b"Bye")
    if sendmail_raises is not None:
        smtp.sendmail.side_effect = sendmail_raises
    else:
        smtp.sendmail.return_value = sendmail_return if sendmail_return is not None else {}
    return smtp


# ── TestSendReviewEmail ───────────────────────────────────────────────────────

class TestSendReviewEmail:

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_success_logs_smtp_response_dict(self, caplog):
        """On success, the empty sendmail() dict {} is logged explicitly."""
        smtp_mock = _make_smtp_mock(sendmail_return={})

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with caplog.at_level(logging.INFO, logger="build_draft"):
                # Should not raise
                send_review_email("Subject", "<p>html</p>", "test@gmail.com")

        # Must log the SMTP response dict
        assert any("sendmail()" in r.message for r in caplog.records)
        # Must log success line
        assert any("sent successfully" in r.message for r in caplog.records)

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_smtp_exception_raises_email_error(self, caplog):
        """SMTPException on sendmail() must raise EmailError — not be swallowed."""
        smtp_mock = _make_smtp_mock(
            sendmail_raises=smtplib.SMTPException("Connection timed out")
        )

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with pytest.raises(EmailError) as exc_info:
                send_review_email("Subject", "<p>html</p>", "test@gmail.com")

        assert "Failed to send review email" in str(exc_info.value)

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_smtp_exception_does_not_log_sent_successfully(self, caplog):
        """'sent successfully' must NOT appear in logs when SMTP raises."""
        smtp_mock = _make_smtp_mock(
            sendmail_raises=smtplib.SMTPException("Rejected")
        )

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with caplog.at_level(logging.INFO, logger="build_draft"):
                with pytest.raises(EmailError):
                    send_review_email("Subject", "<p>html</p>", "test@gmail.com")

        success_logs = [r.message for r in caplog.records if "sent successfully" in r.message]
        assert success_logs == [], f"Should not log success on failure, got: {success_logs}"

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_smtp_exception_logs_error(self, caplog):
        """An SMTP failure must log at ERROR level."""
        smtp_mock = _make_smtp_mock(
            sendmail_raises=smtplib.SMTPException("Auth failed")
        )

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with caplog.at_level(logging.ERROR, logger="build_draft"):
                with pytest.raises(EmailError):
                    send_review_email("Subject", "<p>html</p>", "test@gmail.com")

        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_logs, "Expected at least one ERROR log on SMTP failure"

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_partial_recipient_rejection_raises_email_error(self, caplog):
        """
        sendmail() returning a non-empty dict means some recipients were rejected.
        This must raise EmailError (not silently succeed).
        """
        refused = {"bad@example.com": (550, b"User unknown")}
        smtp_mock = _make_smtp_mock(sendmail_return=refused)

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with pytest.raises(EmailError) as exc_info:
                send_review_email("Subject", "<p>html</p>", "test@gmail.com")

        assert "rejected recipients" in str(exc_info.value)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_credentials_raises_email_error(self):
        """No GMAIL_USER/GMAIL_APP_PASSWORD → raise EmailError immediately."""
        with pytest.raises(EmailError) as exc_info:
            send_review_email("Subject", "<p>html</p>", "test@gmail.com")

        assert "credentials" in str(exc_info.value).lower()

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com"}, clear=True)
    def test_missing_app_password_raises_email_error(self):
        """GMAIL_APP_PASSWORD missing → raise EmailError."""
        with pytest.raises(EmailError):
            send_review_email("Subject", "<p>html</p>", "test@gmail.com")

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_email_error_is_typed(self):
        """EmailError must be a subclass of NewsletterError."""
        from config import EmailError, NewsletterError
        assert issubclass(EmailError, NewsletterError)

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_connection_error_raises_email_error(self):
        """OSError (e.g. network unreachable) must also be wrapped in EmailError."""
        smtp_mock = _make_smtp_mock()
        smtp_mock.sendmail.side_effect = OSError("Network is unreachable")

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with pytest.raises(EmailError):
                send_review_email("Subject", "<p>html</p>", "test@gmail.com")

    @patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "apppass"})
    def test_starttls_failure_raises_email_error(self):
        """starttls() raising must propagate as EmailError (not uncaught)."""
        smtp_mock = _make_smtp_mock()
        smtp_mock.starttls.side_effect = smtplib.SMTPException("TLS failed")

        with patch("build_draft.smtplib.SMTP", return_value=smtp_mock):
            with pytest.raises(EmailError):
                send_review_email("Subject", "<p>html</p>", "test@gmail.com")
