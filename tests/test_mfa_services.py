# tests/test_mfa_services.py - Tests unitaires des services MFA

import pytest
from services.mfa_totp import TOTPService, totp_service
from services.recovery_codes import RecoveryCodeService, recovery_service
from services.mfa_sms import SMSOTPService
from providers.sms.base import MockSMSProvider


class TestTOTPService:
    """Tests du service TOTP."""

    def test_generate_secret(self):
        """Test génération secret TOTP."""
        secret = TOTPService.generate_secret()

        assert secret is not None
        assert len(secret) == 32  # Base32: 32 caractères
        assert secret.isupper()  # Base32 en majuscules
        assert secret.isalnum()  # Alphanumérique uniquement

    def test_provisioning_uri(self):
        """Test génération URI otpauth."""
        secret = "JBSWY3DPEHPK3PXP"
        account = "user@example.com"

        uri = TOTPService.get_provisioning_uri(secret, account)

        assert uri.startswith("otpauth://totp/")
        assert account in uri
        assert secret in uri
        assert "IT%20SPIRIT%20NOVA" in uri or "IT SPIRIT NOVA" in uri

    def test_generate_qr_code(self):
        """Test génération QR code."""
        uri = "otpauth://totp/IT%20SPIRIT%20NOVA:test@example.com?secret=JBSWY3DPEHPK3PXP&issuer=IT%20SPIRIT%20NOVA"

        qr_code = TOTPService.generate_qr_code(uri)

        assert qr_code.startswith("data:image/png;base64,")
        assert len(qr_code) > 100  # QR code base64 doit être assez long

    def test_verify_totp_valid(self):
        """Test vérification TOTP avec code valide."""
        secret = TOTPService.generate_secret()

        # Générer le code actuel
        current_code = TOTPService.get_current_code(secret)

        # Vérifier
        is_valid = TOTPService.verify_totp(secret, current_code, valid_window=1)

        assert is_valid is True

    def test_verify_totp_invalid(self):
        """Test vérification TOTP avec code invalide."""
        secret = TOTPService.generate_secret()
        invalid_code = "000000"

        is_valid = TOTPService.verify_totp(secret, invalid_code, valid_window=1)

        assert is_valid is False

    def test_verify_totp_non_numeric(self):
        """Test vérification TOTP avec code non numérique."""
        secret = TOTPService.generate_secret()
        invalid_code = "ABCDEF"

        is_valid = TOTPService.verify_totp(secret, invalid_code, valid_window=1)

        assert is_valid is False

    def test_enroll_user(self):
        """Test enrôlement complet."""
        secret, uri, qr_code = TOTPService.enroll_user("test@example.com")

        assert len(secret) == 32
        assert uri.startswith("otpauth://totp/")
        assert qr_code.startswith("data:image/png;base64,")

        # Vérifier que le code généré avec ce secret est valide
        current_code = TOTPService.get_current_code(secret)
        assert TOTPService.verify_totp(secret, current_code, valid_window=1)


class TestRecoveryCodeService:
    """Tests du service recovery codes."""

    def test_generate_codes(self):
        """Test génération recovery codes."""
        codes = RecoveryCodeService.generate_codes(10)

        assert len(codes) == 10

        for code in codes:
            assert "-" in code  # Format: XXXX-XXXX
            assert len(code) == 9  # 4 + 1 (tiret) + 4
            parts = code.split("-")
            assert len(parts) == 2
            assert len(parts[0]) == 4
            assert len(parts[1]) == 4
            assert parts[0].isupper()
            assert parts[1].isupper()

    def test_hash_code(self):
        """Test hash d'un recovery code."""
        code = "AB12-CD34"
        hashed = RecoveryCodeService.hash_code(code)

        assert hashed is not None
        assert len(hashed) > 20  # Hash bcrypt est long
        assert hashed != code  # Ne doit pas être en clair

    def test_hash_codes(self):
        """Test hash de plusieurs codes."""
        codes = RecoveryCodeService.generate_codes(5)
        hashes = RecoveryCodeService.hash_codes(codes)

        assert len(hashes) == 5

        for h in hashes:
            assert len(h) > 20

    def test_verify_code_valid(self):
        """Test vérification code valide."""
        code = "AB12-CD34"
        hashed = RecoveryCodeService.hash_code(code)

        is_valid = RecoveryCodeService.verify_code(code, hashed)

        assert is_valid is True

    def test_verify_code_invalid(self):
        """Test vérification code invalide."""
        code = "AB12-CD34"
        wrong_code = "ZZ99-YY88"
        hashed = RecoveryCodeService.hash_code(code)

        is_valid = RecoveryCodeService.verify_code(wrong_code, hashed)

        assert is_valid is False

    def test_verify_code_case_insensitive(self):
        """Test vérification insensible à la casse."""
        code = "AB12-CD34"
        hashed = RecoveryCodeService.hash_code(code)

        # Tester avec minuscules
        is_valid = RecoveryCodeService.verify_code("ab12-cd34", hashed)

        assert is_valid is True

    def test_verify_and_consume_valid(self):
        """Test vérification et consommation d'un code valide."""
        codes = RecoveryCodeService.generate_codes(5)
        hashes = RecoveryCodeService.hash_codes(codes)

        # Utiliser le 3ème code
        remaining = RecoveryCodeService.verify_and_consume(codes[2], hashes)

        assert remaining is not None
        assert len(remaining) == 4  # 5 - 1 = 4

        # Réessayer avec le même code (doit échouer)
        remaining2 = RecoveryCodeService.verify_and_consume(codes[2], remaining)

        assert remaining2 is None

    def test_verify_and_consume_invalid(self):
        """Test consommation d'un code invalide."""
        codes = RecoveryCodeService.generate_codes(5)
        hashes = RecoveryCodeService.hash_codes(codes)

        # Code inexistant
        remaining = RecoveryCodeService.verify_and_consume("ZZ99-YY88", hashes)

        assert remaining is None

    def test_mask_code(self):
        """Test masquage des codes."""
        code = "AB12-CD34"
        masked = RecoveryCodeService.mask_code(code)

        assert masked == "****-34"

    def test_count_remaining(self):
        """Test compteur de codes restants."""
        codes = RecoveryCodeService.generate_codes(10)
        hashes = RecoveryCodeService.hash_codes(codes)

        count = RecoveryCodeService.count_remaining(hashes)
        assert count == 10

        # Consommer 3 codes
        remaining = RecoveryCodeService.verify_and_consume(codes[0], hashes)
        remaining = RecoveryCodeService.verify_and_consume(codes[1], remaining)
        remaining = RecoveryCodeService.verify_and_consume(codes[2], remaining)

        count = RecoveryCodeService.count_remaining(remaining)
        assert count == 7

        # None doit retourner 0
        count = RecoveryCodeService.count_remaining(None)
        assert count == 0


class TestSMSOTPService:
    """Tests du service SMS OTP."""

    @pytest.mark.asyncio
    async def test_send_otp_success(self):
        """Test envoi OTP SMS (mock)."""
        mock_provider = MockSMSProvider()
        sms_service = SMSOTPService(sms_provider=mock_provider)

        user_id = 123
        phone = "+33612345678"

        result = await sms_service.send_otp(user_id, phone)

        assert result["success"] is True
        assert result["message_id"] is not None
        assert "expires_at" in result

        # Vérifier que le mock a bien enregistré
        sent = mock_provider.get_sent_messages()
        assert len(sent) == 1
        assert sent[0]["to"] == phone
        assert "NOVA" in sent[0]["message"]

    @pytest.mark.asyncio
    async def test_verify_otp_valid(self):
        """Test vérification OTP valide."""
        mock_provider = MockSMSProvider()
        sms_service = SMSOTPService(sms_provider=mock_provider)

        user_id = 123
        phone = "+33612345678"

        # Envoyer OTP
        send_result = await sms_service.send_otp(user_id, phone)
        assert send_result["success"] is True

        # Récupérer le code depuis le stockage interne (pour test)
        otp_data = sms_service._get_otp_data(user_id)
        assert otp_data is not None
        code = otp_data["otp"]

        # Vérifier avec le bon code
        is_valid = await sms_service.verify_otp(user_id, code)

        assert is_valid is True

        # Réessayer (doit échouer car consommé)
        is_valid2 = await sms_service.verify_otp(user_id, code)

        assert is_valid2 is False

    @pytest.mark.asyncio
    async def test_verify_otp_invalid(self):
        """Test vérification OTP invalide."""
        mock_provider = MockSMSProvider()
        sms_service = SMSOTPService(sms_provider=mock_provider)

        user_id = 123
        phone = "+33612345678"

        # Envoyer OTP
        await sms_service.send_otp(user_id, phone)

        # Vérifier avec mauvais code
        is_valid = await sms_service.verify_otp(user_id, "000000")

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_otp_max_attempts(self):
        """Test verrouillage après 3 tentatives."""
        mock_provider = MockSMSProvider()
        sms_service = SMSOTPService(sms_provider=mock_provider)

        user_id = 123
        phone = "+33612345678"

        # Envoyer OTP
        await sms_service.send_otp(user_id, phone)

        # 3 tentatives avec mauvais code
        for _ in range(3):
            is_valid = await sms_service.verify_otp(user_id, "000000")
            assert is_valid is False

        # 4ème tentative: OTP supprimé
        is_valid = await sms_service.verify_otp(user_id, "000000")
        assert is_valid is False

        # Vérifier que l'OTP est supprimé
        otp_data = sms_service._get_otp_data(user_id)
        assert otp_data is None

    @pytest.mark.asyncio
    async def test_verify_otp_no_otp_sent(self):
        """Test vérification sans OTP envoyé."""
        mock_provider = MockSMSProvider()
        sms_service = SMSOTPService(sms_provider=mock_provider)

        user_id = 999

        # Tenter de vérifier sans avoir envoyé
        is_valid = await sms_service.verify_otp(user_id, "123456")

        assert is_valid is False
