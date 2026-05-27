# services/cache_manager.py
import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from services.security_helpers import escape_soql

# 🔧 CORRECTION : Import Redis avec gestion d'erreur
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis non disponible - utilisation du cache mémoire uniquement")

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
    """Gestionnaire de cache Redis avec fallback mémoire"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", memory_fallback: bool = True):
        self.redis_url = redis_url
        self.memory_fallback = memory_fallback
        self.redis_client = None
        self.memory_cache = {}
        self.memory_cache_ttl = {}
        
        # 🔧 CORRECTION : Initialisation Redis avec gestion d'erreur
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
                # Test de connexion
                self.redis_client.ping()
                logger.info("✅ Connexion Redis établie")
            except Exception as e:
                logger.warning(f"❌ Connexion Redis échouée: {e}")
                self.redis_client = None
        
        if not self.redis_client and memory_fallback:
            logger.info("🔄 Utilisation du cache mémoire en fallback")

    async def get_cached_data(self, key: str) -> Optional[Dict[str, Any]]:
        """Récupère des données depuis le cache"""
        
        # 🔧 CORRECTION : Essayer Redis en premier si disponible
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(key)
                if cached_data:
                    logger.debug(f"Cache Redis HIT: {key}")
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Erreur lecture Redis: {e}")
        
        # Fallback vers cache mémoire
        if self.memory_fallback:
            if key in self.memory_cache:
                # Vérifier TTL
                if key in self.memory_cache_ttl:
                    if datetime.now() < self.memory_cache_ttl[key]:
                        logger.debug(f"Cache mémoire HIT: {key}")
                        return self.memory_cache[key]
                    else:
                        # Nettoyer l'entrée expirée
                        del self.memory_cache[key]
                        del self.memory_cache_ttl[key]
        
        return None
    
    async def cache_data(self, key: str, data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Met en cache des données"""
        
        # 🔧 CORRECTION : Essayer Redis en premier si disponible
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl, json.dumps(data))
                logger.debug(f"Cache Redis SET: {key}")
                return True
            except Exception as e:
                logger.warning(f"Erreur écriture Redis: {e}")
        
        # Fallback vers cache mémoire
        if self.memory_fallback:
            self.memory_cache[key] = data
            self.memory_cache_ttl[key] = datetime.now() + timedelta(seconds=ttl)
            logger.debug(f"Cache mémoire SET: {key}")
            return True
        
        return False
    
    def generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Génère une clé de cache standardisée"""
        key_parts = [prefix]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return ":".join(key_parts)
    
    def clear_cache(self, pattern: str = None):
        """Nettoie le cache"""
        
        # 🔧 CORRECTION : Nettoyer Redis si disponible
        if self.redis_client:
            try:
                if pattern:
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        self.redis_client.delete(*keys)
                        logger.info(f"Cache Redis nettoyé: {len(keys)} clés supprimées")
                else:
                    self.redis_client.flushall()
                    logger.info("Cache Redis complètement nettoyé")
            except Exception as e:
                logger.warning(f"Erreur nettoyage Redis: {e}")
        
        # Nettoyer cache mémoire
        if self.memory_fallback:
            if pattern:
                keys_to_remove = [k for k in self.memory_cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self.memory_cache[key]
                    self.memory_cache_ttl.pop(key, None)
                logger.info(f"Cache mémoire nettoyé: {len(keys_to_remove)} clés supprimées")
            else:
                self.memory_cache.clear()
                self.memory_cache_ttl.clear()
                logger.info("Cache mémoire complètement nettoyé")
    
    # 🔧 CORRECTION : Méthode pour nettoyer les entrées expirées
    def cleanup_expired_entries(self):
        """Nettoie les entrées expirées du cache mémoire"""
        if not self.memory_fallback:
            return
        
        current_time = datetime.now()
        expired_keys = []
        
        for key, expiry_time in self.memory_cache_ttl.items():
            if current_time >= expiry_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.memory_cache.pop(key, None)
            self.memory_cache_ttl.pop(key, None)
        
        if expired_keys:
            logger.debug(f"Nettoyage: {len(expired_keys)} entrées expirées supprimées")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache"""
        stats = {
            "redis_available": self.redis_client is not None,
            "memory_fallback": self.memory_fallback,
            "memory_cache_size": len(self.memory_cache),
            "memory_cache_keys": list(self.memory_cache.keys())
        }
        
        if self.redis_client:
            try:
                info = self.redis_client.info()
                stats["redis_info"] = {
                    "used_memory": info.get("used_memory_human"),
                    "connected_clients": info.get("connected_clients"),
                    "keyspace_hits": info.get("keyspace_hits"),
                    "keyspace_misses": info.get("keyspace_misses")
                }
            except Exception as e:
                stats["redis_error"] = str(e)
        
        return stats
    async def save_workflow_state(self, task_id: str, state_data: Dict) -> bool:
        """Sauvegarde l'état d'un workflow"""
        try:
            key = f"workflow_state:{task_id}"
            serialized_data = json.dumps(state_data, default=str)
            await self.redis_client.setex(key, 3600, serialized_data)  # 1h TTL
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde état workflow {task_id}: {str(e)}")
            return False

    async def get_workflow_state(self, task_id: str) -> Dict:
        """Récupère l'état d'un workflow"""
        try:
            key = f"workflow_state:{task_id}"
            data = await self.redis_client.get(key)
            return json.loads(data) if data else {}
        except Exception as e:
            logger.error(f"Erreur récupération état workflow {task_id}: {str(e)}")
            return {}
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
        
        logger.info("Cache référentiel initialisé")
    
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
        if not client_name or client_name.strip() == "":
            logger.error("❌ Nom de client vide ou None fourni à cache_client")
            return       
              
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
        if not client_name or client_name.strip() == "":
            logger.error("❌ Nom de client vide ou None fourni à cache_client")
            return
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
                "sap_read", 
                {"endpoint": "/Items?$filter=Discontinued eq 'tNO'&$top=200", "method": "GET"}
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
            "query": f"""
                SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry
                FROM Account
                WHERE UPPER(Name) = UPPER('{escape_soql(client_name)}')
                LIMIT 1
                """.strip()
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
            "query": f"""
                SELECT Id, Name, AccountNumber
                FROM Account
                WHERE UPPER(Name) LIKE UPPER('%{escape_soql(client_name[:5])}%')
                ORDER BY Name
                LIMIT 5
                """.strip()
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
        "sap_search",
        {"query": search_criteria, "entity_type": "Items", "limit": 10}
    )
    
    if product_search.get("success"):
        products = product_search.get("data", [])
        await referential_cache.cache_product_suggestions(search_criteria, products)
        return products
    
    return []