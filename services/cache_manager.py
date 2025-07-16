# services/cache_manager.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json

# Import optionnel de Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Entrée de cache avec métadonnées"""
    data: Any
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def is_valid(self) -> bool:
        return not self.is_expired()
class RedisCacheManager:
    """Gestionnaire de cache Redis pour performances"""

    def __init__(self):
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
                # Test de connexion
                self.redis_client.ping()
                self.redis_available = True
            except Exception as e:
                logger.warning(f"Redis non disponible, utilisation du cache mémoire: {e}")
                self.redis_available = False
                self.memory_cache = {}
        else:
            logger.warning("Module redis non installé, utilisation du cache mémoire")
            self.redis_available = False
            self.memory_cache = {}

        self.default_ttl = 3600  # 1 heure
    
    async def get_cached_data(self, key: str) -> Optional[Any]:
        """Récupération données mises en cache"""
        if self.redis_available:
            try:
                cached = self.redis_client.get(key)
                return json.loads(cached) if cached else None
            except Exception:
                return None
        else:
            # Utiliser le cache mémoire
            return self.memory_cache.get(key)

    async def cache_data(self, key: str, data: Any, ttl: int = None) -> bool:
        """Mise en cache des données"""
        if self.redis_available:
            try:
                self.redis_client.setex(
                    key,
                    ttl or self.default_ttl,
                    json.dumps(data)
                )
                return True
            except Exception:
                return False
        else:
            # Utiliser le cache mémoire
            self.memory_cache[key] = data
            return True
    
    def generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Génération clé de cache standardisée"""
        params = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
        return f"{prefix}:{params}"
class ReferentialCache:
    """Cache intelligent pour accélérer la validation client/produit"""
    
    def __init__(self):
        self._client_cache: Dict[str, CacheEntry] = {}
        self._product_cache: Dict[str, CacheEntry] = {}
        self._suggestion_cache: Dict[str, CacheEntry] = {}
        
        # Configuration des TTL (Time To Live)
        self.CLIENT_TTL = timedelta(hours=2)      # Clients changent peu
        self.PRODUCT_TTL = timedelta(minutes=30)  # Stocks plus dynamiques
        self.SUGGESTION_TTL = timedelta(hours=1)  # Suggestions peuvent évoluer
        
        logger.info("🚀 Cache référentiel initialisé")
    
    # ==================== CACHE CLIENTS ====================
    
    async def get_client_suggestions(self, client_name: str) -> Optional[List[Dict]]:
        """Récupère les suggestions client depuis le cache"""
        cache_key = f"suggestions_{client_name.lower().strip()}"
        
        if cache_key in self._suggestion_cache:
            entry = self._suggestion_cache[cache_key]
            if entry.is_valid():
                entry.hit_count += 1
                logger.info(f"📂 Cache HIT suggestions client: {client_name}")
                return entry.data
            else:
                # Nettoyer l'entrée expirée
                del self._suggestion_cache[cache_key]
        
        return None
    
    async def cache_client_suggestions(self, client_name: str, suggestions: List[Dict]):
        """Met en cache les suggestions client"""
        cache_key = f"suggestions_{client_name.lower().strip()}"
        
        entry = CacheEntry(
            data=suggestions,
            created_at=datetime.now(),
            expires_at=datetime.now() + self.SUGGESTION_TTL
        )
        
        self._suggestion_cache[cache_key] = entry
        logger.info(f"💾 Suggestions client mises en cache: {client_name} ({len(suggestions)} suggestions)")
    
    async def get_client_by_name(self, client_name: str) -> Optional[Dict]:
        """Récupère un client par nom depuis le cache"""
        cache_key = f"client_{client_name.lower().strip()}"
        
        if cache_key in self._client_cache:
            entry = self._client_cache[cache_key]
            if entry.is_valid():
                entry.hit_count += 1
                logger.info(f"📂 Cache HIT client: {client_name}")
                return entry.data
        
        return None
    
    async def cache_client(self, client_name: str, client_data: Dict):
        """Met en cache les données client"""
        cache_key = f"client_{client_name.lower().strip()}"
        
        entry = CacheEntry(
            data=client_data,
            created_at=datetime.now(),
            expires_at=datetime.now() + self.CLIENT_TTL
        )
        
        self._client_cache[cache_key] = entry
        logger.info(f"💾 Client mis en cache: {client_name}")
    
    # ==================== CACHE PRODUITS ====================
    
    async def get_product_suggestions(self, search_criteria: str) -> Optional[List[Dict]]:
        """Récupère les suggestions produit depuis le cache"""
        cache_key = f"product_search_{search_criteria.lower().strip()}"
        
        if cache_key in self._product_cache:
            entry = self._product_cache[cache_key]
            if entry.is_valid():
                entry.hit_count += 1
                logger.info(f"📂 Cache HIT produits: {search_criteria}")
                return entry.data
        
        return None
    
    async def cache_product_suggestions(self, search_criteria: str, products: List[Dict]):
        """Met en cache les résultats de recherche produit"""
        cache_key = f"product_search_{search_criteria.lower().strip()}"
        
        entry = CacheEntry(
            data=products,
            created_at=datetime.now(),
            expires_at=datetime.now() + self.PRODUCT_TTL
        )
        
        self._product_cache[cache_key] = entry
        logger.info(f"💾 Recherche produit mise en cache: {search_criteria} ({len(products)} résultats)")
    
    async def get_product_by_code(self, product_code: str) -> Optional[Dict]:
        """Récupère un produit par code depuis le cache"""
        cache_key = f"product_{product_code.upper().strip()}"
        
        if cache_key in self._product_cache:
            entry = self._product_cache[cache_key]
            if entry.is_valid():
                entry.hit_count += 1
                logger.info(f"📂 Cache HIT produit: {product_code}")
                return entry.data
        
        return None
    
    async def cache_product(self, product_code: str, product_data: Dict):
        """Met en cache les données produit"""
        cache_key = f"product_{product_code.upper().strip()}"
        
        entry = CacheEntry(
            data=product_data,
            created_at=datetime.now(),
            expires_at=datetime.now() + self.PRODUCT_TTL
        )
        
        self._product_cache[cache_key] = entry
        logger.info(f"💾 Produit mis en cache: {product_code}")
    
    # ==================== PRÉ-CHARGEMENT ====================
    
    async def preload_common_data(self, mcp_connector):
        """Pré-charge les données fréquemment utilisées"""
        logger.info("🔄 Pré-chargement du cache...")
        
        try:
            # Pré-charger les clients les plus actifs (derniers 100)
            recent_clients = await mcp_connector.call_mcp(
                "salesforce_mcp", 
                "salesforce_query",
                {
                    "query": "SELECT Id, Name, AccountNumber, Phone, Email, BillingCity FROM Account ORDER BY LastModifiedDate DESC LIMIT 100"
                }
            )
            
            if recent_clients.get("success"):
                for client in recent_clients.get("data", []):
                    await self.cache_client(client["Name"], client)
                logger.info(f"✅ {len(recent_clients.get('data', []))} clients pré-chargés")
            
            # Pré-charger les produits actifs SAP
            active_products = await mcp_connector.call_mcp(
                "sap_mcp",
                "get_items", 
                {"active_only": True, "limit": 200}
            )
            
            if active_products.get("success"):
                for product in active_products.get("data", []):
                    await self.cache_product(product.get("ItemCode", ""), product)
                logger.info(f"✅ {len(active_products.get('data', []))} produits pré-chargés")
                
        except Exception as e:
            logger.warning(f"⚠️ Erreur pré-chargement cache: {str(e)}")
    
    # ==================== MAINTENANCE ====================
    
    async def cleanup_expired(self):
        """Nettoie les entrées expirées du cache"""
        expired_clients = [k for k, v in self._client_cache.items() if v.is_expired()]
        expired_products = [k for k, v in self._product_cache.items() if v.is_expired()]
        expired_suggestions = [k for k, v in self._suggestion_cache.items() if v.is_expired()]
        
        for key in expired_clients:
            del self._client_cache[key]
        for key in expired_products:
            del self._product_cache[key]
        for key in expired_suggestions:
            del self._suggestion_cache[key]
        
        total_cleaned = len(expired_clients) + len(expired_products) + len(expired_suggestions)
        if total_cleaned > 0:
            logger.info(f"🧹 {total_cleaned} entrées expirées nettoyées")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache"""
        total_hits = sum(entry.hit_count for entry in 
                        [*self._client_cache.values(), *self._product_cache.values(), *self._suggestion_cache.values()])
        
        return {
            "clients_cached": len(self._client_cache),
            "products_cached": len(self._product_cache),
            "suggestions_cached": len(self._suggestion_cache),
            "total_hits": total_hits,
            "cache_efficiency": f"{(total_hits / (len(self._client_cache) + len(self._product_cache) + 1) * 100):.1f}%"
        }

# Instance globale du cache
referential_cache = ReferentialCache()

# ==================== INTÉGRATION WORKFLOW ====================

async def get_cached_client_or_fetch(client_name: str, mcp_connector) -> Dict:
    """Récupère un client depuis le cache ou via MCP si absent"""
    
    # 1. Vérifier le cache d'abord
    cached_client = await referential_cache.get_client_by_name(client_name)
    if cached_client:
        return {"found": True, "data": cached_client, "source": "cache"}
    
    # 2. Vérifier le cache de suggestions
    cached_suggestions = await referential_cache.get_client_suggestions(client_name)
    if cached_suggestions:
        return {
            "found": False, 
            "suggestions": cached_suggestions, 
            "source": "cache",
            "message": f"Client '{client_name}' non trouvé. Voici les clients similaires :"
        }
    
    # 3. Recherche via MCP si pas en cache
    logger.info(f"🔍 Recherche client via MCP: {client_name}")
    
    # Recherche exacte d'abord
    exact_search = await mcp_connector.call_mcp(
        "salesforce_mcp", 
        "salesforce_query",
        {
            "query": f"SELECT Id, Name, AccountNumber, Phone, Email, BillingCity, BillingCountry FROM Account WHERE Name = '{client_name}' LIMIT 1"
        }
    )
    
    if exact_search.get("success") and exact_search.get("data"):
        client_data = exact_search["data"][0]
        await referential_cache.cache_client(client_name, client_data)
        return {"found": True, "data": client_data, "source": "mcp"}
    
    # Recherche floue pour suggestions
    fuzzy_search = await mcp_connector.call_mcp(
        "salesforce_mcp", 
        "salesforce_query", 
        {
            "query": f"SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%{client_name[:5]}%' ORDER BY Name LIMIT 5"
        }
    )
    
    if fuzzy_search.get("success") and fuzzy_search.get("data"):
        suggestions = fuzzy_search["data"]
        await referential_cache.cache_client_suggestions(client_name, suggestions)
        return {
            "found": False, 
            "suggestions": suggestions, 
            "source": "mcp",
            "message": f"Client '{client_name}' non trouvé. Voici les clients similaires :"
        }
    
    return {"found": False, "suggestions": [], "source": "mcp"}

async def get_cached_products_or_fetch(search_criteria: str, mcp_connector) -> List[Dict]:
    """Récupère des produits depuis le cache ou via MCP si absent"""
    
    # 1. Vérifier le cache d'abord
    cached_products = await referential_cache.get_product_suggestions(search_criteria)
    if cached_products:
        return cached_products
    
    # 2. Recherche via MCP si pas en cache
    logger.info(f"🔍 Recherche produits via MCP: {search_criteria}")
    
    # Recherche dans SAP par caractéristiques
    product_search = await mcp_connector.call_mcp(
        "sap_mcp",
        "search_items_by_description",
        {"search_term": search_criteria, "limit": 10}
    )
    
    if product_search.get("success"):
        products = product_search.get("data", [])
        await referential_cache.cache_product_suggestions(search_criteria, products)
        return products
    
    return []