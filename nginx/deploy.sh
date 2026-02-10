#!/bin/bash
# Script de déploiement automatique pour nova-rondot.itspirit.ovh
# Lance l'installation complète de Nginx + SSL + NOVA Backend

set -e  # Arrêter en cas d'erreur

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="nova-rondot.itspirit.ovh"
EMAIL="admin@itspirit.ovh"  # Email pour Let's Encrypt
NOVA_DIR="/opt/nova-server"  # Répertoire d'installation NOVA
VENV_DIR="$NOVA_DIR/.venv"
SERVICE_USER="www-data"

echo ""
echo "=========================================="
echo "  Déploiement NOVA-SERVER"
echo "  Domaine : $DOMAIN"
echo "=========================================="
echo ""

# Vérifier si on est root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERREUR] Ce script doit être exécuté en root (sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}[OK] Exécution en root${NC}"

# Vérifier la distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo -e "${GREEN}[OK] Distribution détectée : $OS${NC}"
else
    echo -e "${RED}[ERREUR] Distribution non reconnue${NC}"
    exit 1
fi

# Fonction d'installation des paquets
install_packages() {
    echo ""
    echo -e "${BLUE}=== Installation des paquets ===${NC}"

    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        apt update
        apt install -y nginx certbot python3-certbot-nginx python3-pip python3-venv git curl
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        yum install -y epel-release
        yum install -y nginx certbot python3-certbot-nginx python3-pip python3-venv git curl
    else
        echo -e "${RED}[ERREUR] Distribution non supportée${NC}"
        exit 1
    fi

    echo -e "${GREEN}[OK] Paquets installés${NC}"
}

# Vérifier DNS
check_dns() {
    echo ""
    echo -e "${BLUE}=== Vérification DNS ===${NC}"

    if host $DOMAIN > /dev/null 2>&1; then
        IP=$(host $DOMAIN | grep "has address" | awk '{print $4}')
        echo -e "${GREEN}[OK] DNS configuré : $DOMAIN -> $IP${NC}"
    else
        echo -e "${YELLOW}[ATTENTION] DNS non résolu pour $DOMAIN${NC}"
        echo "Assurez-vous que le DNS pointe vers ce serveur avant de continuer."
        read -p "Continuer quand même ? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Installer Nginx
setup_nginx() {
    echo ""
    echo -e "${BLUE}=== Configuration Nginx ===${NC}"

    # Activer et démarrer Nginx
    systemctl enable nginx
    systemctl start nginx

    # Copier la configuration
    if [ -f "nova-rondot.conf" ]; then
        cp nova-rondot.conf /etc/nginx/sites-available/$DOMAIN.conf

        # Créer le lien symbolique
        ln -sf /etc/nginx/sites-available/$DOMAIN.conf /etc/nginx/sites-enabled/

        # Supprimer la config par défaut
        rm -f /etc/nginx/sites-enabled/default

        echo -e "${GREEN}[OK] Configuration Nginx copiée${NC}"
    else
        echo -e "${RED}[ERREUR] Fichier nova-rondot.conf introuvable${NC}"
        exit 1
    fi

    # Tester la configuration
    if nginx -t; then
        echo -e "${GREEN}[OK] Configuration Nginx valide${NC}"
        systemctl reload nginx
    else
        echo -e "${RED}[ERREUR] Configuration Nginx invalide${NC}"
        exit 1
    fi
}

# Obtenir certificat SSL
setup_ssl() {
    echo ""
    echo -e "${BLUE}=== Installation certificat SSL ===${NC}"

    # Arrêter Nginx temporairement
    systemctl stop nginx

    # Obtenir le certificat
    certbot certonly --standalone -d $DOMAIN --email $EMAIL --agree-tos --non-interactive

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[OK] Certificat SSL installé${NC}"

        # Mettre à jour la configuration Nginx avec les bons chemins
        sed -i "s|ssl_certificate .*|ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;|g" /etc/nginx/sites-available/$DOMAIN.conf
        sed -i "s|ssl_certificate_key .*|ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;|g" /etc/nginx/sites-available/$DOMAIN.conf

        # Redémarrer Nginx
        systemctl start nginx

        # Configurer le renouvellement automatique
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -

        echo -e "${GREEN}[OK] Renouvellement automatique configuré${NC}"
    else
        echo -e "${RED}[ERREUR] Impossible d'obtenir le certificat SSL${NC}"
        systemctl start nginx
        exit 1
    fi
}

# Installer NOVA Backend
setup_nova() {
    echo ""
    echo -e "${BLUE}=== Installation NOVA Backend ===${NC}"

    # Créer le répertoire
    mkdir -p $NOVA_DIR
    cd $NOVA_DIR

    # Cloner le repo ou copier les fichiers
    echo "Note : Vous devez copier manuellement les fichiers NOVA dans $NOVA_DIR"
    echo "ou cloner depuis un repository Git."

    # Créer l'environnement virtuel
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv $VENV_DIR
        echo -e "${GREEN}[OK] Environnement virtuel créé${NC}"
    fi

    # Activer l'environnement virtuel
    source $VENV_DIR/bin/activate

    # Installer les dépendances si requirements.txt existe
    if [ -f "requirements.txt" ]; then
        pip install --upgrade pip
        pip install -r requirements.txt
        echo -e "${GREEN}[OK] Dépendances installées${NC}"
    else
        echo -e "${YELLOW}[ATTENTION] requirements.txt non trouvé${NC}"
    fi

    # Configurer .env si nécessaire
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}[ATTENTION] Fichier .env non trouvé${NC}"
        echo "Créez le fichier .env avec la configuration appropriée."
    fi

    # Ajuster les permissions
    chown -R $SERVICE_USER:$SERVICE_USER $NOVA_DIR

    deactivate
}

# Créer le service systemd
setup_service() {
    echo ""
    echo -e "${BLUE}=== Configuration service systemd ===${NC}"

    cat > /etc/systemd/system/nova-server.service <<EOF
[Unit]
Description=NOVA-SERVER Backend FastAPI
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$NOVA_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python main.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

    # Recharger systemd
    systemctl daemon-reload

    # Activer et démarrer le service
    systemctl enable nova-server
    systemctl start nova-server

    # Vérifier le statut
    sleep 3
    if systemctl is-active --quiet nova-server; then
        echo -e "${GREEN}[OK] Service NOVA démarré${NC}"
    else
        echo -e "${RED}[ERREUR] Le service NOVA n'a pas pu démarrer${NC}"
        echo "Vérifiez les logs : journalctl -u nova-server -n 50"
        exit 1
    fi
}

# Configurer le pare-feu
setup_firewall() {
    echo ""
    echo -e "${BLUE}=== Configuration pare-feu ===${NC}"

    if command -v ufw &> /dev/null; then
        ufw --force enable
        ufw default deny incoming
        ufw default allow outgoing
        ufw allow ssh
        ufw allow 'Nginx Full'
        ufw reload

        echo -e "${GREEN}[OK] Pare-feu configuré (UFW)${NC}"
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --permanent --add-service=ssh
        firewall-cmd --reload

        echo -e "${GREEN}[OK] Pare-feu configuré (firewalld)${NC}"
    else
        echo -e "${YELLOW}[ATTENTION] Aucun pare-feu détecté${NC}"
    fi
}

# Tests finaux
run_tests() {
    echo ""
    echo -e "${BLUE}=== Tests de vérification ===${NC}"

    # Test backend local
    echo -n "Test backend local... "
    if curl -s http://127.0.0.1:8000/health > /dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}ERREUR${NC}"
    fi

    # Test domaine HTTPS
    echo -n "Test HTTPS... "
    if curl -s https://$DOMAIN/health > /dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}ERREUR${NC}"
    fi

    # Test redirection
    echo -n "Test redirection root... "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/)
    if [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}CODE: $HTTP_CODE${NC}"
    fi
}

# Afficher le résumé
show_summary() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}  DÉPLOIEMENT TERMINÉ${NC}"
    echo "=========================================="
    echo ""
    echo "URLs d'accès :"
    echo "  - Mail-to-Biz : https://$DOMAIN/"
    echo "  - API Backend : https://$DOMAIN/api"
    echo "  - Health Check : https://$DOMAIN/health"
    echo "  - Documentation : https://$DOMAIN/docs"
    echo ""
    echo "Commandes utiles :"
    echo "  - Logs Nginx : tail -f /var/log/nginx/nova-rondot.error.log"
    echo "  - Logs NOVA : journalctl -u nova-server -f"
    echo "  - Redémarrer NOVA : systemctl restart nova-server"
    echo "  - Recharger Nginx : systemctl reload nginx"
    echo ""
    echo "Statut des services :"
    systemctl is-active nova-server && echo -e "  - NOVA Backend : ${GREEN}ACTIF${NC}" || echo -e "  - NOVA Backend : ${RED}INACTIF${NC}"
    systemctl is-active nginx && echo -e "  - Nginx : ${GREEN}ACTIF${NC}" || echo -e "  - Nginx : ${RED}INACTIF${NC}"
    echo ""
}

# Exécution principale
main() {
    # Demander confirmation
    echo "Ce script va installer et configurer :"
    echo "  - Nginx (reverse proxy)"
    echo "  - Certbot (certificat SSL)"
    echo "  - NOVA Backend (service systemd)"
    echo "  - Pare-feu (UFW/firewalld)"
    echo ""
    read -p "Continuer ? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation annulée."
        exit 0
    fi

    # Installation
    install_packages
    check_dns
    setup_nginx
    setup_ssl
    setup_nova
    setup_service
    setup_firewall
    run_tests
    show_summary
}

# Lancer le script
main
