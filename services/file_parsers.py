"""
Module de parsing multi-format pour les fichiers de tarifs fournisseurs.
Supporte: PDF, Excel (.xlsx, .xls), CSV, images (via OCR)
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Extensions supportées par type
SUPPORTED_EXTENSIONS = {
    'pdf': ['.pdf'],
    'excel': ['.xlsx', '.xls'],
    'csv': ['.csv'],
    'image': ['.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif']
}

ALL_SUPPORTED_EXTENSIONS = [ext for exts in SUPPORTED_EXTENSIONS.values() for ext in exts]


def get_file_type(file_path: str) -> Optional[str]:
    """Détermine le type de fichier basé sur l'extension."""
    ext = Path(file_path).suffix.lower()
    for file_type, extensions in SUPPORTED_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return None


def is_supported_file(file_path: str) -> bool:
    """Vérifie si le fichier est supporté."""
    return get_file_type(file_path) is not None


def extract_price(text: str) -> Optional[float]:
    """Extrait un prix d'une chaîne de texte."""
    if not text:
        return None

    # Patterns pour les prix
    patterns = [
        r'(\d+[.,]\d{2})\s*(?:€|EUR|euro)',  # 123.45 € ou 123,45 EUR
        r'(?:€|EUR)\s*(\d+[.,]\d{2})',        # € 123.45
        r'(\d+[.,]\d{2,3})',                   # Juste un nombre décimal
        r'(\d+)\s*(?:€|EUR|euro)',             # 123 €
    ]

    for pattern in patterns:
        match = re.search(pattern, str(text), re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '.')
            try:
                return float(price_str)
            except ValueError:
                continue
    return None


def extract_reference(text: str) -> Optional[str]:
    """Extrait une référence produit d'une chaîne."""
    if not text:
        return None

    # Patterns communs pour les références
    patterns = [
        r'(?:ref|réf|reference|référence)[.:\s]*([A-Z0-9\-_]+)',
        r'([A-Z]{2,4}[\-_]?\d{3,})',  # XX-1234 ou ABC1234
        r'(\d{6,})',                    # Code numérique 6+ chiffres
    ]

    for pattern in patterns:
        match = re.search(pattern, str(text), re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


class PDFParser:
    """Parser pour les fichiers PDF."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        """Parse un fichier PDF et extrait les données de tarifs."""
        products = []

        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF non installé. Installation: pip install pymupdf")
            try:
                # Fallback sur pdfplumber
                import pdfplumber
                return PDFParser._parse_with_pdfplumber(file_path)
            except ImportError:
                logger.error("Aucune bibliothèque PDF disponible")
                return []

        try:
            doc = fitz.open(file_path)
            full_text = ""

            for page in doc:
                full_text += page.get_text()

            doc.close()

            # Extraction des données structurées
            products = PDFParser._extract_products_from_text(full_text, file_path)

        except Exception as e:
            logger.error(f"Erreur parsing PDF {file_path}: {e}")

        return products

    @staticmethod
    def _parse_with_pdfplumber(file_path: str) -> List[Dict[str, Any]]:
        """Parse PDF avec pdfplumber (fallback)."""
        import pdfplumber
        products = []

        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"

                    # Extraction des tableaux
                    tables = page.extract_tables()
                    for table in tables:
                        products.extend(PDFParser._parse_table(table, file_path))

                # Si pas de tableaux, extraire du texte
                if not products:
                    products = PDFParser._extract_products_from_text(full_text, file_path)

        except Exception as e:
            logger.error(f"Erreur pdfplumber {file_path}: {e}")

        return products

    @staticmethod
    def _parse_table(table: List[List], file_path: str) -> List[Dict[str, Any]]:
        """Parse un tableau extrait d'un PDF."""
        products = []
        if not table or len(table) < 2:
            return products

        # Première ligne = en-têtes
        headers = [str(h).lower() if h else '' for h in table[0]]

        # Mapping des colonnes
        col_mapping = {
            'reference': ['ref', 'réf', 'reference', 'référence', 'code', 'sku', 'article'],
            'designation': ['designation', 'désignation', 'description', 'libellé', 'libelle', 'nom', 'produit'],
            'price': ['prix', 'price', 'tarif', 'pu', 'p.u.', 'montant', 'ht'],
            'supplier': ['fournisseur', 'supplier', 'marque', 'brand'],
            'delivery': ['délai', 'delai', 'livraison', 'delivery', 'dispo']
        }

        col_indices = {}
        for field, keywords in col_mapping.items():
            for i, header in enumerate(headers):
                if any(kw in header for kw in keywords):
                    col_indices[field] = i
                    break

        # Parser les lignes de données
        for row in table[1:]:
            if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                continue

            product = {
                'supplier_reference': row[col_indices.get('reference')] if 'reference' in col_indices and col_indices['reference'] < len(row) else None,
                'designation': row[col_indices.get('designation')] if 'designation' in col_indices and col_indices['designation'] < len(row) else None,
                'unit_price': extract_price(row[col_indices.get('price')]) if 'price' in col_indices and col_indices['price'] < len(row) else None,
                'supplier_name': row[col_indices.get('supplier')] if 'supplier' in col_indices and col_indices['supplier'] < len(row) else None,
                'delivery_time': row[col_indices.get('delivery')] if 'delivery' in col_indices and col_indices['delivery'] < len(row) else None,
                'currency': 'EUR',
                'additional_data': {'source_file': Path(file_path).name}
            }

            # Ne garder que si on a au moins une référence ou une désignation
            if product['supplier_reference'] or product['designation']:
                products.append(product)

        return products

    @staticmethod
    def _extract_products_from_text(text: str, file_path: str) -> List[Dict[str, Any]]:
        """Extraction heuristique de produits depuis du texte brut."""
        products = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue

            # Chercher des patterns de produits
            ref = extract_reference(line)
            price = extract_price(line)

            if ref or price:
                product = {
                    'supplier_reference': ref,
                    'designation': line[:200] if len(line) > 200 else line,
                    'unit_price': price,
                    'currency': 'EUR',
                    'additional_data': {'source_file': Path(file_path).name, 'raw_line': line}
                }
                products.append(product)

        return products


class ExcelParser:
    """Parser pour les fichiers Excel."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        """Parse un fichier Excel et extrait les données de tarifs."""
        products = []

        try:
            import openpyxl
        except ImportError:
            logger.warning("openpyxl non installé. Installation: pip install openpyxl")
            return []

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)

            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                products.extend(ExcelParser._parse_sheet(sheet, file_path, sheet_name))

            wb.close()

        except Exception as e:
            logger.error(f"Erreur parsing Excel {file_path}: {e}")

        return products

    @staticmethod
    def _parse_sheet(sheet, file_path: str, sheet_name: str) -> List[Dict[str, Any]]:
        """Parse une feuille Excel."""
        products = []

        # Lire toutes les lignes
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return products

        # Trouver la ligne d'en-têtes (première ligne non vide)
        header_row_idx = 0
        for i, row in enumerate(rows):
            if row and any(cell is not None for cell in row):
                header_row_idx = i
                break

        headers = [str(h).lower().strip() if h else '' for h in rows[header_row_idx]]

        # Mapping des colonnes
        col_mapping = {
            'reference': ['ref', 'réf', 'reference', 'référence', 'code', 'sku', 'article', 'code article', 'code produit'],
            'designation': ['designation', 'désignation', 'description', 'libellé', 'libelle', 'nom', 'produit', 'intitulé'],
            'price': ['prix', 'price', 'tarif', 'pu', 'p.u.', 'montant', 'prix ht', 'prix unitaire', 'pu ht'],
            'supplier': ['fournisseur', 'supplier', 'marque', 'brand', 'fabricant'],
            'delivery': ['délai', 'delai', 'livraison', 'delivery', 'dispo', 'disponibilité'],
            'category': ['catégorie', 'categorie', 'category', 'famille', 'type'],
            'brand': ['marque', 'brand', 'fabricant']
        }

        col_indices = {}
        for field, keywords in col_mapping.items():
            for i, header in enumerate(headers):
                if any(kw in header for kw in keywords):
                    col_indices[field] = i
                    break

        # Parser les lignes de données
        for row in rows[header_row_idx + 1:]:
            if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                continue

            def get_cell(field):
                if field in col_indices and col_indices[field] < len(row):
                    val = row[col_indices[field]]
                    return str(val).strip() if val is not None else None
                return None

            def get_price(field):
                val = get_cell(field)
                if val:
                    return extract_price(val)
                # Essayer directement si c'est un nombre
                if field in col_indices and col_indices[field] < len(row):
                    cell_val = row[col_indices[field]]
                    if isinstance(cell_val, (int, float)):
                        return float(cell_val)
                return None

            product = {
                'supplier_reference': get_cell('reference'),
                'designation': get_cell('designation'),
                'unit_price': get_price('price'),
                'supplier_name': get_cell('supplier'),
                'delivery_time': get_cell('delivery'),
                'category': get_cell('category'),
                'brand': get_cell('brand'),
                'currency': 'EUR',
                'additional_data': {
                    'source_file': Path(file_path).name,
                    'sheet_name': sheet_name
                }
            }

            # Ne garder que si on a au moins une référence ou une désignation
            if product['supplier_reference'] or product['designation']:
                products.append(product)

        return products


class CSVParser:
    """Parser pour les fichiers CSV."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        """Parse un fichier CSV et extrait les données de tarifs."""
        import csv
        products = []

        # Essayer différents encodages et délimiteurs
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        delimiters = [';', ',', '\t', '|']

        for encoding in encodings:
            for delimiter in delimiters:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        # Lire quelques lignes pour vérifier
                        sample = f.read(4096)
                        f.seek(0)

                        # Vérifier si le délimiteur est présent
                        if delimiter not in sample:
                            continue

                        reader = csv.DictReader(f, delimiter=delimiter)

                        for row in reader:
                            product = CSVParser._parse_row(row, file_path)
                            if product:
                                products.append(product)

                        if products:
                            return products

                except (UnicodeDecodeError, csv.Error):
                    continue
                except Exception as e:
                    logger.error(f"Erreur CSV {file_path}: {e}")
                    continue

        return products

    @staticmethod
    def _parse_row(row: Dict, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse une ligne CSV."""
        # Normaliser les clés
        normalized = {k.lower().strip(): v for k, v in row.items() if k}

        # Mapping des champs
        field_mapping = {
            'reference': ['ref', 'réf', 'reference', 'référence', 'code', 'sku', 'article'],
            'designation': ['designation', 'désignation', 'description', 'libellé', 'libelle', 'nom', 'produit'],
            'price': ['prix', 'price', 'tarif', 'pu', 'p.u.', 'montant', 'prix ht'],
            'supplier': ['fournisseur', 'supplier', 'marque'],
            'delivery': ['délai', 'delai', 'livraison', 'delivery']
        }

        def find_value(field_names):
            for name in field_names:
                for key in normalized:
                    if name in key:
                        return normalized[key]
            return None

        ref = find_value(field_mapping['reference'])
        designation = find_value(field_mapping['designation'])

        if not ref and not designation:
            return None

        price_str = find_value(field_mapping['price'])

        return {
            'supplier_reference': ref,
            'designation': designation,
            'unit_price': extract_price(price_str) if price_str else None,
            'supplier_name': find_value(field_mapping['supplier']),
            'delivery_time': find_value(field_mapping['delivery']),
            'currency': 'EUR',
            'additional_data': {'source_file': Path(file_path).name}
        }


class ImageParser:
    """Parser pour les images (via OCR)."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        """Parse une image via OCR et extrait les données."""
        products = []

        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.warning("pytesseract ou Pillow non installé. Installation: pip install pytesseract pillow")
            return []

        try:
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image, lang='fra+eng')

            # Extraction heuristique du texte OCR
            products = PDFParser._extract_products_from_text(text, file_path)

        except Exception as e:
            logger.error(f"Erreur OCR image {file_path}: {e}")

        return products


def parse_file(file_path: str) -> List[Dict[str, Any]]:
    """Parse un fichier selon son type et retourne les produits extraits."""
    file_type = get_file_type(file_path)

    if not file_type:
        logger.warning(f"Type de fichier non supporté: {file_path}")
        return []

    parsers = {
        'pdf': PDFParser.parse,
        'excel': ExcelParser.parse,
        'csv': CSVParser.parse,
        'image': ImageParser.parse
    }

    parser = parsers.get(file_type)
    if parser:
        logger.info(f"Parsing {file_type}: {file_path}")
        return parser(file_path)

    return []


def scan_folder(folder_path: str, recursive: bool = True) -> List[Dict[str, Any]]:
    """Scanne un dossier et retourne la liste des fichiers supportés."""
    folder = Path(folder_path)

    if not folder.exists():
        logger.error(f"Dossier non trouvé: {folder_path}")
        return []

    files = []

    if recursive:
        for ext in ALL_SUPPORTED_EXTENSIONS:
            files.extend(folder.rglob(f"*{ext}"))
    else:
        for ext in ALL_SUPPORTED_EXTENSIONS:
            files.extend(folder.glob(f"*{ext}"))

    result = []
    for file_path in files:
        stat = file_path.stat()
        result.append({
            'path': str(file_path),
            'name': file_path.name,
            'type': get_file_type(str(file_path)),
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime)
        })

    return result
