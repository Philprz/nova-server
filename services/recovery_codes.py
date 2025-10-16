# services/recovery_codes.py - Génération et vérification des codes de récupération

import secrets
import string
from typing import List, Optional
import bcrypt


class RecoveryCodeService:
    """
    Service pour gérer les recovery codes (codes de secours one-time).
    Format: XXXX-XXXX (8 caractères alphanumériques, séparés par tiret).

    Workflow:
    1. Génération: generate_codes(n=10) -> ["ABCD-1234", ...]
    2. Hash: hash_codes(codes) -> [hash1, hash2, ...]
    3. Stockage: user.recovery_codes_hashes = hashes (JSONB)
    4. Vérification: verify_code(plain, hashes) -> (is_valid, remaining_hashes)
    5. Consommation: si valide, retirer le hash utilisé de la liste
    """

    CODE_LENGTH = 8  # Total caractères (sans tiret)
    SEPARATOR = "-"
    ALPHABET = string.ascii_uppercase + string.digits  # A-Z + 0-9

    @staticmethod
    def generate_codes(n: int = 10) -> List[str]:
        """
        Génère n recovery codes aléatoires.

        Args:
            n: Nombre de codes à générer (défaut: 10)

        Returns:
            Liste de codes au format "XXXX-XXXX"

        Exemple:
            ["AB12-CD34", "EF56-GH78", ...]
        """
        codes = []
        for _ in range(n):
            # Générer 8 caractères aléatoires
            code_chars = "".join(secrets.choice(RecoveryCodeService.ALPHABET) for _ in range(RecoveryCodeService.CODE_LENGTH))

            # Insérer le séparateur au milieu (XXXX-XXXX)
            half = RecoveryCodeService.CODE_LENGTH // 2
            formatted_code = f"{code_chars[:half]}{RecoveryCodeService.SEPARATOR}{code_chars[half:]}"

            codes.append(formatted_code)

        return codes

    @staticmethod
    def hash_code(code: str) -> str:
        """
        Hash un recovery code avec bcrypt.

        Args:
            code: Code en clair (ex: "AB12-CD34")

        Returns:
            Hash bcrypt (string)

        Note: bcrypt inclut le salt automatiquement.
        """
        # Normaliser: upper + sans espaces
        normalized = code.upper().strip()

        # Hash avec bcrypt
        hashed = bcrypt.hashpw(normalized.encode("utf-8"), bcrypt.gensalt())

        return hashed.decode("utf-8")

    @staticmethod
    def hash_codes(codes: List[str]) -> List[str]:
        """
        Hash une liste de recovery codes.

        Args:
            codes: Liste de codes en clair

        Returns:
            Liste de hash bcrypt

        Usage:
            codes = RecoveryCodeService.generate_codes(10)
            hashes = RecoveryCodeService.hash_codes(codes)
            # Stocker hashes en DB, afficher codes à l'utilisateur UNE SEULE FOIS
        """
        return [RecoveryCodeService.hash_code(code) for code in codes]

    @staticmethod
    def verify_code(code_plain: str, code_hash: str) -> bool:
        """
        Vérifie un recovery code contre son hash.

        Args:
            code_plain: Code saisi par l'utilisateur
            code_hash: Hash bcrypt stocké en DB

        Returns:
            True si match, False sinon

        Note: Utilise bcrypt.checkpw (constant-time comparison).
        """
        # Normaliser input
        normalized = code_plain.upper().strip()

        try:
            return bcrypt.checkpw(normalized.encode("utf-8"), code_hash.encode("utf-8"))
        except (ValueError, AttributeError):
            # Hash invalide ou format incorrect
            return False

    @staticmethod
    def verify_and_consume(code_plain: str, hashes: List[str]) -> Optional[List[str]]:
        """
        Vérifie un code et retourne la liste mise à jour (sans le code consommé).

        Args:
            code_plain: Code saisi
            hashes: Liste des hash encore valides

        Returns:
            Liste mise à jour si code valide, None si invalide

        Usage:
            new_hashes = RecoveryCodeService.verify_and_consume(user_code, user.recovery_codes_hashes)
            if new_hashes is not None:
                # Code valide! Mettre à jour DB
                user.recovery_codes_hashes = new_hashes
                # Authentifier l'utilisateur
            else:
                # Code invalide
        """
        for i, code_hash in enumerate(hashes):
            if RecoveryCodeService.verify_code(code_plain, code_hash):
                # Code valide! Retirer ce hash de la liste
                remaining_hashes = hashes[:i] + hashes[i + 1:]
                return remaining_hashes

        # Aucun code ne match
        return None

    @staticmethod
    def mask_code(code: str) -> str:
        """
        Masque un recovery code pour affichage sécurisé.

        Args:
            code: Code au format "XXXX-XXXX"

        Returns:
            Code masqué: "****-XX34" (affiche uniquement les 2 derniers caractères)

        Usage:
            masked_codes = [RecoveryCodeService.mask_code(c) for c in codes]
            # Afficher pour que l'utilisateur puisse identifier ses codes sans les révéler
        """
        if len(code) < 4:
            return "****"

        # Garder les 2 derniers caractères après le séparateur
        parts = code.split(RecoveryCodeService.SEPARATOR)
        if len(parts) == 2:
            return f"****{RecoveryCodeService.SEPARATOR}{parts[1][-2:]}"
        else:
            # Fallback si format inattendu
            return f"****{code[-2:]}"

    @staticmethod
    def count_remaining(hashes: Optional[List[str]]) -> int:
        """
        Compte le nombre de recovery codes restants.

        Args:
            hashes: Liste de hash (peut être None)

        Returns:
            Nombre de codes restants (0 si None)
        """
        return len(hashes) if hashes else 0


# Instance globale
recovery_service = RecoveryCodeService()
