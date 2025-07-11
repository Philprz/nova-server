def load_optional_modules():
    MODULES = {
        'assistant': 'routes.routes_intelligent_assistant',
        'devis': 'routes.routes_devis',
        'clients': 'routes.routes_clients'
    }
    
    loaded = {}
    for name, path in MODULES.items():
        try:
            loaded[name] = __import__(path, fromlist=['router'])
        except ImportError as e:
            logger.warning(f"Module {name} non disponible")
    return loaded