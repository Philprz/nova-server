// =====================================
// MODIFICATION : templates/intelligent_assistant.html
// SECTION : JavaScript pour Progression Temps Réel
// =====================================

// Variables globales pour le tracking de progression
let currentTaskId = null;
let pollingInterval = null;
let progressDisplayActive = false;

// Fonction modifiée pour sendMessage avec progression temps réel
async function sendMessage() {
    if (isProcessing) return;
    
    const input = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Ajouter le message utilisateur
    addUserMessage(message);
    
    // Vider et réinitialiser l'input
    input.value = '';
    input.style.height = 'auto';
    sendButton.disabled = true;
    
    // État de traitement
    isProcessing = true;
    sendButton.classList.add('sending');
    
    // 🔧 MODIFICATION : Afficher la progression au lieu de l'indicateur de frappe
    showProgressDisplay();
    
    try {
        // 🔧 MODIFICATION : Utiliser l'API asynchrone au lieu de l'API synchrone
        const response = await fetch('/progress/start_quote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                prompt: message,
                draft_mode: isDraftMode
            })
        });
        
        if (!response.ok) {
            throw new Error(`Erreur serveur: ${response.status}`);
        }
        
        const result = await response.json();
        
        // 🔧 MODIFICATION : Démarrer le polling de progression
        if (result.task_id) {
            currentTaskId = result.task_id;
            console.log("🔄 Démarrage polling pour task:", currentTaskId);
            startProgressPolling(currentTaskId);
        } else {
            throw new Error("Aucun task_id reçu du serveur");
        }
        
    } catch (error) {
        console.error("❌ Erreur:", error);
        hideProgressDisplay();
        addAssistantMessage({
            response: {
                message: `❌ Erreur: ${error.message}`,
                suggestions: ['Réessayer', 'Reformuler la demande', 'Vérifier la connexion']
            }
        });
        
        // Réinitialiser l'état
        isProcessing = false;
        sendButton.classList.remove('sending');
        input.focus();
    }
}

// 🆕 NOUVELLE FONCTION : Affichage de la progression
function showProgressDisplay() {
    // Masquer l'indicateur de frappe standard
    hideTypingIndicator();
    
    // Créer ou afficher la zone de progression
    let progressContainer = document.getElementById('progressContainer');
    
    if (!progressContainer) {
        progressContainer = document.createElement('div');
        progressContainer.id = 'progressContainer';
        progressContainer.className = 'progress-container';
        progressContainer.innerHTML = `
            <div class="progress-message">
                <div class="progress-avatar">⚙️</div>
                <div class="progress-content">
                    <div class="progress-title">🤖 NOVA traite votre demande...</div>
                    <div class="progress-details">
                        <div class="progress-bar-container">
                            <div class="progress-bar" id="progressBar">
                                <div class="progress-bar-fill" id="progressBarFill" style="width: 0%"></div>
                            </div>
                            <div class="progress-percentage" id="progressPercentage">0%</div>
                        </div>
                        <div class="progress-step" id="progressStep">Initialisation...</div>
                        <div class="progress-phases" id="progressPhases"></div>
                    </div>
                </div>
            </div>
        `;
        
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.appendChild(progressContainer);
    }
    
    progressContainer.style.display = 'block';
    progressDisplayActive = true;
    scrollToBottom();
}

// 🆕 NOUVELLE FONCTION : Masquer la progression
function hideProgressDisplay() {
    const progressContainer = document.getElementById('progressContainer');
    if (progressContainer) {
        progressContainer.style.display = 'none';
    }
    progressDisplayActive = false;
    
    // Arrêter le polling si actif
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// 🆕 NOUVELLE FONCTION : Démarrer le polling de progression
async function startProgressPolling(taskId) {
    let attempts = 0;
    const maxAttempts = 240; // 4 minutes max (toutes les secondes)
    
    pollingInterval = setInterval(async () => {
        attempts++;
        
        if (attempts > maxAttempts) {
            clearInterval(pollingInterval);
            updateProgressError("Timeout - La génération prend trop de temps");
            return;
        }
        
        try {
            const response = await fetch(`/progress/quote_status/${taskId}?detailed=true`);
            if (!response.ok) {
                throw new Error(`Status ${response.status}`);
            }
            
            const progress = await response.json();
            updateProgressDisplay(progress);
            
            // Vérifier si terminé
            if (progress.status === 'completed') {
                clearInterval(pollingInterval);
                pollingInterval = null;
                
                // Masquer la progression et afficher le résultat
                hideProgressDisplay();
                showQuoteResult(progress.result || progress);
                resetProcessingState();
                
            } else if (progress.status === 'failed') {
                clearInterval(pollingInterval);
                pollingInterval = null;
                
                hideProgressDisplay();
                addAssistantMessage({
                    response: {
                        message: `❌ Erreur: ${progress.error || 'Échec de la génération'}`,
                        suggestions: ['Réessayer', 'Modifier la demande', 'Contacter le support']
                    }
                });
                resetProcessingState();
            }
            
        } catch (error) {
            console.error("❌ Erreur polling:", error);
            // Ne pas arrêter le polling pour une erreur temporaire
            updateProgressError(`Erreur de communication (tentative ${attempts}/${maxAttempts})`);
        }
    }, 1000); // Polling toutes les secondes
}

// 🆕 NOUVELLE FONCTION : Mettre à jour l'affichage de progression
function updateProgressDisplay(progress) {
    if (!progressDisplayActive) return;
    
    const progressBarFill = document.getElementById('progressBarFill');
    const progressPercentage = document.getElementById('progressPercentage');
    const progressStep = document.getElementById('progressStep');
    const progressPhases = document.getElementById('progressPhases');
    
    if (!progressBarFill) return;
    
    // Mettre à jour la barre de progression
    const overallProgress = progress.overall_progress || 0;
    progressBarFill.style.width = `${overallProgress}%`;
    progressPercentage.textContent = `${overallProgress}%`;
    
    // Mettre à jour l'étape courante
    const currentStepTitle = progress.current_step_title || 'En cours...';
    progressStep.textContent = `📋 ${currentStepTitle}`;
    
    // Afficher les phases détaillées si disponibles
    if (progress.phases && progressPhases) {
        let phasesHtml = '';
        Object.values(progress.phases).forEach(phase => {
            if (phase.steps && phase.steps.length > 0) {
                phasesHtml += `<div class="progress-phase">`;
                phasesHtml += `<div class="phase-title">${phase.name}</div>`;
                
                phase.steps.forEach(step => {
                    const statusIcon = getStepStatusIcon(step.status);
                    const statusClass = `step-${step.status}`;
                    phasesHtml += `
                        <div class="progress-phase-step ${statusClass}">
                            ${statusIcon} ${step.title}
                        </div>
                    `;
                });
                
                phasesHtml += `</div>`;
            }
        });
        progressPhases.innerHTML = phasesHtml;
    }
    
    scrollToBottom();
}

// 🆕 NOUVELLE FONCTION : Icônes de statut des étapes
function getStepStatusIcon(status) {
    switch (status) {
        case 'completed': return '✅';
        case 'running': return '⚙️';
        case 'failed': return '❌';
        case 'pending': return '⏳';
        default: return '📋';
    }
}

// 🆕 NOUVELLE FONCTION : Afficher erreur de progression
function updateProgressError(errorMessage) {
    const progressStep = document.getElementById('progressStep');
    if (progressStep) {
        progressStep.textContent = `⚠️ ${errorMessage}`;
        progressStep.style.color = '#ef4444';
    }
}

// 🆕 NOUVELLE FONCTION : Réinitialiser l'état de traitement
function resetProcessingState() {
    isProcessing = false;
    currentTaskId = null;
    
    const sendButton = document.getElementById('sendButton');
    if (sendButton) {
        sendButton.classList.remove('sending');
    }
    
    const input = document.getElementById('chatInput');
    if (input) {
        input.focus();
    }
}

// 🆕 NOUVELLE FONCTION : Afficher le résultat final
function showQuoteResult(result) {
    let resultMessage = "✅ Devis traité avec succès !";
    let suggestions = ['Voir le devis', 'Créer un nouveau devis', 'Modifier le devis'];
    
    if (result && result.message) {
        resultMessage = result.message;
    }
    
    if (result && result.suggestions) {
        suggestions = result.suggestions;
    }
    
    addAssistantMessage({
        response: {
            message: resultMessage,
            suggestions: suggestions
        }
    });
}

// 🔧 MODIFICATION : Fonction existante hideTypingIndicator modifiée
function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.classList.remove('show');
    }
}