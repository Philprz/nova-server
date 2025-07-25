# services/module_loader.py - VERSION CORRIGÉE
import importlib
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ModuleConfig:
    """Configuration d'un module optionnel"""
    module_path: str
    prefix: str = ""
    tags: list = None
    required: bool = False
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

class ModuleLoader:
    """Gestionnaire centralisé de chargement des modules optionnels"""
    
    def __init__(self):
        """CORRECTION: __init__ ne prend aucun paramètre"""
        self.loaded_modules: Dict[str, Any] = {}
        self.failed_modules: Dict[str, str] = {}
        
    def load_module(self, name: str, config: ModuleConfig) -> Optional[Any]:
        """Charge un module individuel avec gestion d'erreur"""
        try:
            module = importlib.import_module(config.module_path)
            
            # Validation que le module a un router
            if not hasattr(module, 'router'):
                raise ImportError(f"Module {name} n'a pas d'attribut 'router'")
                
            self.loaded_modules[name] = {
                'module': module,
                'router': module.router,
                'config': config,
                'loaded': True
            }
            
            logger.info(f"Module {name} charge depuis {config.module_path}")
            return module
            
        except ImportError as e:
            error_msg = f"Module {name} non disponible: {e}"
            self.failed_modules[name] = error_msg
            
            if config.required:
                logger.error(f"[ERROR] {error_msg} (REQUIS)")
                raise
            else:
                logger.warning(f"[WARNING] {error_msg}")
                
        except Exception as e:
            error_msg = f"Erreur lors du chargement du module {name}: {e}"
            self.failed_modules[name] = error_msg
            logger.error(f"[ERROR] {error_msg}")
                
        return None
    
    def load_modules(self, modules_config: Dict[str, ModuleConfig]) -> Dict[str, Any]:
        """Charge tous les modules depuis une configuration"""
        for name, config in modules_config.items():
            self.load_module(name, config)
            
        return self.loaded_modules
    
    async def load_all_modules(self):
        """Méthode pour compatibilité avec l'ancien code"""
        # Cette méthode est conservée pour la compatibilité
        logger.info(f"Modules disponibles: {len(self.loaded_modules)}")
        return self.loaded_modules
    
    def get_loaded_modules(self) -> Dict[str, Any]:
        """Retourne la liste des modules chargés"""
        return self.loaded_modules
    
    def get_failed_modules(self) -> Dict[str, str]:
        """Retourne la liste des modules qui ont échoué au chargement"""
        return self.failed_modules
    
    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut complet du chargeur de modules"""
        total_modules = len(self.loaded_modules) + len(self.failed_modules)
        
        return {
            "total_modules": total_modules,
            "loaded_count": len(self.loaded_modules),
            "failed_count": len(self.failed_modules),
            "success_rate": len(self.loaded_modules) / total_modules * 100 if total_modules > 0 else 0,
            "loaded_modules": list(self.loaded_modules.keys()),
            "failed_modules": list(self.failed_modules.keys())
        }