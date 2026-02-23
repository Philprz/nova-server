"""
tests/test_product_classification.py

Tests unitaires pour la logique de classification produit.

Règle métier (spécification RONDOT) :
  Un produit est considéré "vraiment nouveau" (CAS_4_NP = Nouveau Produit) uniquement si :
    - Aucun ItemCode SAP trouvé (sap_item_code is None)
    - Aucun historique d'achat (purchase_history est vide / None)
    - Aucun prix SAP connu (sap_price is None)

  Si l'article EXISTE dans SAP (ItemCode non nul) mais n'a jamais été vendu,
  c'est du "sans historique de vente" — pas un "nouveau produit".
"""

from typing import Optional, List


# ---------------------------------------------------------------------------
# Fonction utilitaire de classification (miroir de la logique backend)
# ---------------------------------------------------------------------------

class ProductAnalysis:
    """Représente les données produit à classifier."""
    def __init__(
        self,
        sap_item_code: Optional[str] = None,
        sap_price: Optional[float] = None,
        purchase_history: Optional[List[dict]] = None,
    ):
        self.sap_item_code = sap_item_code
        self.sap_price = sap_price
        self.purchase_history = purchase_history


def is_new_product(item: ProductAnalysis) -> bool:
    """
    Retourne True uniquement si le produit est totalement absent de SAP.
    Un article présent dans le catalogue SAP (sap_item_code non nul)
    avec CAS_4_NP signifie "jamais vendu" — pas "nouveau produit".
    """
    return (
        item.sap_item_code is None
        and item.sap_price is None
        and not item.purchase_history
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_existing_sap_product_not_marked_new():
    """Un produit trouvé dans SAP n'est pas un nouveau produit."""
    item = ProductAnalysis(
        sap_item_code="A12768",
        sap_price=0.13,
        purchase_history=[],
    )
    assert is_new_product(item) is False, (
        "A12768 existe dans SAP — ne doit pas être marqué 'Nouveau Produit'"
    )


def test_existing_sap_product_with_history_not_marked_new():
    """Un produit SAP avec historique de vente n'est pas nouveau."""
    item = ProductAnalysis(
        sap_item_code="A03024",
        sap_price=1200.0,
        purchase_history=[{"doc_num": "INV-001", "price": 1100.0}],
    )
    assert is_new_product(item) is False


def test_truly_new_product_no_sap():
    """Un produit sans code SAP, sans prix, sans historique = vraiment nouveau."""
    item = ProductAnalysis(
        sap_item_code=None,
        sap_price=None,
        purchase_history=None,
    )
    assert is_new_product(item) is True


def test_truly_new_product_empty_history():
    """Même logique avec une liste vide explicite pour purchase_history."""
    item = ProductAnalysis(
        sap_item_code=None,
        sap_price=None,
        purchase_history=[],
    )
    # purchase_history vide → falsy → considéré comme aucun historique
    assert is_new_product(item) is True


def test_product_with_sap_code_but_no_price_not_marked_new():
    """Un article présent dans SAP sans prix connu n'est pas 'nouveau produit'."""
    item = ProductAnalysis(
        sap_item_code="C431M-020",
        sap_price=None,       # Prix non renseigné dans le cache
        purchase_history=None,
    )
    assert is_new_product(item) is False, (
        "C431M-020 a un ItemCode SAP — ne doit pas être classé Nouveau Produit "
        "même si son prix n'est pas connu"
    )


def test_product_with_only_supplier_price():
    """
    Si un article a un prix fournisseur (sap_price) mais pas de code SAP,
    il n'est pas encore dans SAP → nouveau produit.
    """
    item = ProductAnalysis(
        sap_item_code=None,
        sap_price=45.0,  # Prix vient du tarif fournisseur, pas du catalogue SAP
        purchase_history=None,
    )
    # sap_price non nul → is_new_product retourne False (on a au moins un prix)
    assert is_new_product(item) is False


# ---------------------------------------------------------------------------
# Exécution directe pour vérification rapide
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_existing_sap_product_not_marked_new,
        test_existing_sap_product_with_history_not_marked_new,
        test_truly_new_product_no_sap,
        test_truly_new_product_empty_history,
        test_product_with_sap_code_but_no_price_not_marked_new,
        test_product_with_only_supplier_price,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passés")
