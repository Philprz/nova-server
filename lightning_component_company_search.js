// CompanySearchComponent.js - Composant Lightning pour Salesforce
// Intégration de l'agent de recherche d'entreprises NOVA dans Salesforce

import { LightningElement, track, wire, api } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import { NavigationMixin } from 'lightning/navigation';

export default class CompanySearchComponent extends NavigationMixin(LightningElement) {
    @api recordId; // ID de l'enregistrement actuel (Account, Opportunity, etc.)
    @api objectApiName; // Nom de l'objet actuel
    
    // State
    @track searchTerm = '';
    @track searchResults = [];
    @track selectedCompany = null;
    @track isLoading = false;
    @track showResults = false;
    @track showSuggestions = false;
    @track suggestions = [];
    @track errorMessage = '';
    @track enrichmentData = null;
    
    // Configuration
    novaApiUrl = 'http://178.33.233.120:8200'; // URL de l'API NOVA
    maxResults = 10;
    
    // Computed properties
    get hasResults() {
        return this.searchResults && this.searchResults.length > 0;
    }
    
    get hasSuggestions() {
        return this.suggestions && this.suggestions.length > 0;
    }
    
    get isSearchDisabled() {
        return this.isLoading || !this.searchTerm.trim();
    }
    
    get searchButtonLabel() {
        return this.isLoading ? 'Recherche...' : 'Rechercher';
    }
    
    get searchButtonIcon() {
        return this.isLoading ? 'utility:spinner' : 'utility:search';
    }
    
    // Event handlers
    handleSearchTermChange(event) {
        this.searchTerm = event.target.value;
        this.clearPreviousResults();
        
        // Auto-suggestions après 3 caractères
        if (this.searchTerm.length >= 3) {
            this.debounceGetSuggestions();
        }
    }
    
    handleKeyPress(event) {
        if (event.key === 'Enter' && !this.isSearchDisabled) {
            this.handleSearch();
        }
    }
    
    async handleSearch() {
        if (!this.searchTerm.trim()) {
            this.showError('Veuillez entrer un nom d\'entreprise ou un SIREN');
            return;
        }
        
        this.isLoading = true;
        this.clearPreviousResults();
        
        try {
            const response = await fetch(`${this.novaApiUrl}/companies/search/${encodeURIComponent(this.searchTerm)}?max_results=${this.maxResults}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.searchResults = data.companies || [];
                this.showResults = true;
                
                if (this.searchResults.length === 0) {
                    this.getSuggestions();
                } else {
                    this.showSuggestions = false;
                }
                
                this.showSuccess(`${this.searchResults.length} entreprise(s) trouvée(s)`);
            } else {
                this.showError(data.error || 'Erreur lors de la recherche');
            }
            
        } catch (error) {
            console.error('Erreur recherche:', error);
            this.showError('Erreur de connexion à l\'API NOVA: ' + error.message);
        } finally {
            this.isLoading = false;
        }
    }
    
    async handleCompanySelect(event) {
        const companyIndex = event.currentTarget.dataset.index;
        const company = this.searchResults[companyIndex];
        
        if (!company) return;
        
        this.selectedCompany = company;
        
        // Enrichissement automatique des données
        await this.enrichCompanyData(company);
        
        // Mise à jour de l'enregistrement actuel si applicable
        if (this.recordId && this.objectApiName) {
            await this.updateCurrentRecord(company);
        }
        
        this.showSuccess(`Entreprise sélectionnée: ${company.denomination}`);
    }
    
    async handleSirenValidation(event) {
        const siren = event.currentTarget.dataset.siren;
        
        if (!siren) return;
        
        this.isLoading = true;
        
        try {
            const response = await fetch(`${this.novaApiUrl}/companies/validate_siren`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ siren })
            });
            
            const data = await response.json();
            
            if (data.valid) {
                this.showSuccess(`SIREN ${siren} est valide`);
            } else {
                this.showWarning(`SIREN ${siren} est invalide`);
            }
            
        } catch (error) {
            console.error('Erreur validation SIREN:', error);
            this.showError('Erreur lors de la validation du SIREN');
        } finally {
            this.isLoading = false;
        }
    }
    
    async handleSuggestionSelect(event) {
        const suggestion = event.currentTarget.dataset.suggestion;
        this.searchTerm = suggestion;
        this.showSuggestions = false;
        await this.handleSearch();
    }
    
    handleClearResults() {
        this.clearPreviousResults();
        this.searchTerm = '';
        this.selectedCompany = null;
        this.enrichmentData = null;
    }
    
    async handleEnrichCurrentRecord() {
        if (!this.recordId || !this.selectedCompany) {
            this.showError('Aucune entreprise sélectionnée ou enregistrement actuel non défini');
            return;
        }
        
        this.isLoading = true;
        
        try {
            await this.updateCurrentRecord(this.selectedCompany);
            this.showSuccess('Enregistrement enrichi avec succès');
        } catch (error) {
            console.error('Erreur enrichissement:', error);
            this.showError('Erreur lors de l\'enrichissement');
        } finally {
            this.isLoading = false;
        }
    }
    
    handleCreateNewAccount() {
        if (!this.selectedCompany) {
            this.showError('Aucune entreprise sélectionnée');
            return;
        }
        
        // Navigation vers la création d'un nouveau compte
        this[NavigationMixin.Navigate]({
            type: 'standard__objectPage',
            attributes: {
                objectApiName: 'Account',
                actionName: 'new'
            },
            state: {
                defaultFieldValues: this.getAccountDefaults()
            }
        });
    }
    
    // Helper methods
    async enrichCompanyData(company) {
        if (!company.siren) return;
        
        try {
            const response = await fetch(`${this.novaApiUrl}/companies/siren/${company.siren}`);
            const data = await response.json();
            
            if (data.success) {
                this.enrichmentData = {
                    ...data.company,
                    enriched_at: new Date().toISOString()
                };
            }
        } catch (error) {
            console.error('Erreur enrichissement:', error);
        }
    }
    
    async updateCurrentRecord(company) {
        if (!this.recordId || !company) return;
        
        const fields = {
            Id: this.recordId,
            Name: company.denomination,
            CompanyCode__c: company.siren, // Champ personnalisé pour SIREN
            Industry: this.mapIndustryCode(company.activite_principale),
            Type: this.mapLegalForm(company.forme_juridique),
            Description: `Données enrichies via NOVA - Source: ${company.source}`,
            EnrichmentDate__c: new Date().toISOString(),
            CompanyStatus__c: company.etat_administratif
        };
        
        // Mise à jour via Apex ou LDS
        // Implementation dépend de la configuration Salesforce
        
        return fields;
    }
    
    getAccountDefaults() {
        if (!this.selectedCompany) return {};
        
        return {
            Name: this.selectedCompany.denomination,
            CompanyCode__c: this.selectedCompany.siren,
            Industry: this.mapIndustryCode(this.selectedCompany.activite_principale),
            Type: this.mapLegalForm(this.selectedCompany.forme_juridique),
            Description: `Créé via NOVA - Source: ${this.selectedCompany.source}`
        };
    }
    
    mapIndustryCode(codeApe) {
        // Mapping des codes APE vers les industries Salesforce
        const industryMapping = {
            '70.10Z': 'Consulting',
            '64.19Z': 'Banking',
            '6110Z': 'Telecommunications',
            '4711D': 'Retail',
            '29.10Z': 'Manufacturing',
            '4910Z': 'Transportation'
        };
        
        return industryMapping[codeApe] || 'Other';
    }
    
    mapLegalForm(formeJuridique) {
        // Mapping des formes juridiques vers les types Salesforce
        const typeMapping = {
            '5599': 'Customer - Direct',
            '5800': 'Customer - Direct',
            '7389': 'Partner'
        };
        
        return typeMapping[formeJuridique] || 'Prospect';
    }
    
    async getSuggestions() {
        if (!this.searchTerm || this.searchTerm.length < 3) return;
        
        try {
            const response = await fetch(`${this.novaApiUrl}/companies/suggestions/${encodeURIComponent(this.searchTerm)}`);
            const data = await response.json();
            
            if (data.success && data.suggestions) {
                this.suggestions = data.suggestions;
                this.showSuggestions = true;
            }
        } catch (error) {
            console.error('Erreur suggestions:', error);
        }
    }
    
    debounceGetSuggestions = this.debounce(this.getSuggestions, 500);
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    clearPreviousResults() {
        this.searchResults = [];
        this.showResults = false;
        this.showSuggestions = false;
        this.suggestions = [];
        this.errorMessage = '';
    }
    
    // Toast notifications
    showSuccess(message) {
        this.dispatchEvent(new ShowToastEvent({
            title: 'Succès',
            message: message,
            variant: 'success'
        }));
    }
    
    showError(message) {
        this.dispatchEvent(new ShowToastEvent({
            title: 'Erreur',
            message: message,
            variant: 'error'
        }));
        this.errorMessage = message;
    }
    
    showWarning(message) {
        this.dispatchEvent(new ShowToastEvent({
            title: 'Attention',
            message: message,
            variant: 'warning'
        }));
    }
    
    // Lifecycle hooks
    connectedCallback() {
        console.log('CompanySearchComponent connecté');
        console.log('Record ID:', this.recordId);
        console.log('Object API Name:', this.objectApiName);
    }
    
    disconnectedCallback() {
        console.log('CompanySearchComponent déconnecté');
    }
    
    renderedCallback() {
        // Focus sur le champ de recherche au premier rendu
        if (!this.hasRendered) {
            const searchInput = this.template.querySelector('lightning-input[data-id="search-input"]');
            if (searchInput) {
                searchInput.focus();
            }
            this.hasRendered = true;
        }
    }
}
