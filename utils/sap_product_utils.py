"""
Fonction utilitaire pour lister rapidement les produits SAP
À utiliser dans un notebook ou script Python
"""

import asyncio
from services.mcp_connector import MCPConnector
import pandas as pd
from typing import Optional, Dict, Any, List


async def list_sap_products(
    limit: int = 50, 
    search_term: Optional[str] = None,
    fields_to_show: Optional[List[str]] = None,
    show_all_fields: bool = False
) -> pd.DataFrame:
    """
    Liste les produits SAP sous forme de DataFrame pandas
    
    Args:
        limit: Nombre maximum de produits à récupérer
        search_term: Terme de recherche optionnel (recherche dans nom et code)
        fields_to_show: Liste des champs à afficher (None = champs par défaut)
        show_all_fields: Si True, affiche tous les champs disponibles
        
    Returns:
        DataFrame pandas avec les produits
        
    Example:
        # Lister 10 produits
        df = await list_sap_products(10)
        
        # Chercher des imprimantes
        df = await list_sap_products(50, "printer")
        
        # Afficher tous les champs
        df = await list_sap_products(20, show_all_fields=True)
    """
    try:
        connector = MCPConnector()
        
        # Construire l'endpoint
        endpoint = f"/Items?$top={limit}"
        
        if search_term:
            # Recherche dans plusieurs champs
            filters = []
            search_lower = search_term.lower()
            
            # Recherche dans le nom et le code
            filters.append(f"contains(tolower(ItemName),'{search_lower}')")
            filters.append(f"contains(tolower(ItemCode),'{search_lower}')")
            
            # Ajouter la description si elle existe
            filters.append(f"contains(tolower(U_Description),'{search_lower}')")
            
            endpoint += f"&$filter={' or '.join(filters)}"
            
        endpoint += "&$orderby=ItemCode"
        
        print(f"🔄 Récupération des produits SAP...")
        
        # Appel SAP
        result = await connector.call_sap_mcp("sap_read", {
            "endpoint": endpoint,
            "method": "GET"
        })
        
        if "error" in result:
            print(f"❌ Erreur: {result['error']}")
            return pd.DataFrame()
            
        products = result.get("value", [])
        
        if not products:
            print("⚠️ Aucun produit trouvé")
            return pd.DataFrame()
            
        # Créer DataFrame
        df = pd.DataFrame(products)
        
        # Définir les colonnes par défaut si non spécifiées
        if not show_all_fields and fields_to_show is None:
            default_fields = [
                'ItemCode',
                'ItemName',
                'U_Description',
                'U_PrixCatalogue',
                'QuantityOnStock',
                'OnHand',
                'ItemsGroupCode',
                'BarCode',
                'Manufacturer',
                'Valid'
            ]
            # Garder seulement les colonnes qui existent
            fields_to_show = [col for col in default_fields if col in df.columns]
            
        # Filtrer les colonnes si nécessaire
        if not show_all_fields and fields_to_show:
            df = df[fields_to_show]
            
        print(f"✅ {len(products)} produits trouvés")
        
        # Afficher un aperçu des champs disponibles
        if show_all_fields or len(df.columns) > 10:
            print(f"\n📊 Champs disponibles ({len(df.columns)}):")
            for i, col in enumerate(sorted(df.columns), 1):
                non_null = df[col].notna().sum()
                pct = (non_null / len(df) * 100) if len(df) > 0 else 0
                print(f"   {i:2d}. {col:<30} ({pct:5.1f}% rempli)")
                
        return df
        
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


async def analyze_product_fields(limit: int = 100) -> Dict[str, Any]:
    """
    Analyse détaillée des champs produits SAP
    
    Args:
        limit: Nombre de produits à analyser
        
    Returns:
        Dictionnaire avec l'analyse des champs
    """
    try:
        df = await list_sap_products(limit=limit, show_all_fields=True)
        
        if df.empty:
            return {"error": "Aucun produit trouvé"}
            
        analysis = {
            "total_products": len(df),
            "total_fields": len(df.columns),
            "fields_analysis": {}
        }
        
        for col in df.columns:
            # Analyser chaque colonne
            col_data = df[col]
            non_null = col_data.notna()
            
            field_info = {
                "non_null_count": non_null.sum(),
                "null_count": (~non_null).sum(),
                "fill_rate": f"{(non_null.sum() / len(df) * 100):.1f}%",
                "unique_values": col_data.nunique(),
                "data_type": str(col_data.dtype),
                "examples": []
            }
            
            # Ajouter des exemples de valeurs non-nulles
            examples = col_data[non_null].drop_duplicates().head(5).tolist()
            field_info["examples"] = examples
            
            analysis["fields_analysis"][col] = field_info
            
        # Trier par taux de remplissage
        sorted_fields = sorted(
            analysis["fields_analysis"].items(),
            key=lambda x: x[1]["non_null_count"],
            reverse=True
        )
        
        print("\n📊 ANALYSE DES CHAMPS PRODUITS SAP")
        print("="*60)
        print(f"Produits analysés: {analysis['total_products']}")
        print(f"Nombre de champs: {analysis['total_fields']}")
        print("\n🔝 TOP 20 CHAMPS PAR TAUX DE REMPLISSAGE:")
        print("-"*60)
        
        for field, info in sorted_fields[:20]:
            print(f"\n📌 {field}")
            print(f"   Remplissage: {info['fill_rate']} ({info['non_null_count']}/{analysis['total_products']})")
            print(f"   Valeurs uniques: {info['unique_values']}")
            print(f"   Type: {info['data_type']}")
            if info['examples']:
                print(f"   Exemples: {info['examples'][:3]}")
                
        return analysis
        
    except Exception as e:
        print(f"❌ Erreur analyse: {str(e)}")
        return {"error": str(e)}


# Fonction wrapper pour utilisation simple
def get_sap_products(limit=50, search=None, all_fields=False):
    """
    Wrapper synchrone simple pour récupérer les produits SAP
    
    Example:
        # Dans un notebook ou script
        df = get_sap_products(20)
        df = get_sap_products(search="printer")
    """
    return asyncio.run(list_sap_products(limit, search, show_all_fields=all_fields))


def analyze_sap_catalog(limit=100):
    """
    Wrapper synchrone pour analyser le catalogue SAP
    """
    return asyncio.run(analyze_product_fields(limit))


if __name__ == "__main__":
    # Test rapide
    print("\n🔧 TEST DE LA FONCTION list_sap_products\n")
    df = asyncio.run(list_sap_products(limit=10))
    if not df.empty:
        print("\n📋 Aperçu des produits:")
        print(df.to_string())
    else:
        print("⚠️ Aucun produit récupéré")