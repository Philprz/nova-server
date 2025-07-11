# services/module_loader.py
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
                'config': config
            }
            
            logger.info(f"✅ Module {name} chargé depuis {config.module_path}")
            return module
            
        except ImportError as e:
            error_msg = f"Module {name} non disponible: {e}"
            self.failed_modules[name] = error_msg
            
            if config.required:
                logger.error(f"❌ {error_msg} (REQUIS)")
                raise
            else:
                logger.warning(f"⚠️ {error_msg}")
                
        return None
    
    def load_modules(self, modules_config: Dict[str, ModuleConfig]) -> Dict[str, Any]:
        """Charge tous les modules depuis une configuration"""
        for name, config in modules_config.items():
            self.load_module(name, config)
            
        return self.loaded_modules
    
    def get_loaded_modules(self) -> Dict[str, Any]:
        """Retourne la liste des modules chargés"""
        return self.loaded_modules
    
    def get_status(self) -> Dict[str, str]:
        """Retourne le statut de tous les modules"""
        status = {}
        
        for name in self.loaded_modules:
            status[name] = "loaded"
            
        for name, error in self.failed_modules.items():
            status[name] = "failed"
            
        return status
    
    def register_to_fastapi(self, app, exclude: list = None):
        """Enregistre automatiquement tous les routers chargés"""
        exclude = exclude or []
        
        for name, module_info in self.loaded_modules.items():
            if name in exclude:
                continue
                
            config = module_info['config']
            router = module_info['router']
            
            # Enregistrement avec ou sans préfixe
            kwargs = {'tags': config.tags}
            if config.prefix:
                kwargs['prefix'] = config.prefix
                
            app.include_router(router, **kwargs)
            logger.info(f"✅ Routes {name.title()} enregistrées")

# Instance globale réutilisable            
module_loader = ModuleLoader()