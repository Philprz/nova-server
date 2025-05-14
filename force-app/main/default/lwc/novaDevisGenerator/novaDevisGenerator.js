// force-app/main/default/lwc/novaDevisGenerator/novaDevisGenerator.js
import { LightningElement, track, api, wire } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import { getRecord } from 'lightning/uiRecordApi';
import { createRecord } from 'lightning/uiRecordApi';
import { updateRecord } from 'lightning/uiRecordApi';

export default class NovaDevisGenerator extends LightningElement {
    @api recordId; // Id de l'account ou de l'opportunité depuis la page Salesforce
    @track prompt = '';
    @track isProcessing = false;
    @track showResult = false;
    @track devisResult = null;
    @track error = null;
    @track accountName = '';
    @track selectedAlternatives = {};
    @track showAlternatives = false;

    @wire(getRecord, { recordId: '$recordId', fields: ['Account.Name'] })
    wiredAccount({ error, data }) {
        if (data) {
            this.accountName = data.fields.Name.value;
            this.prompt = `Créer un devis pour le client ${this.accountName} `;
        } else if (error) {
            console.error('Erreur lors du chargement du compte', error);
        }
    }

    handlePromptChange(event) {
        this.prompt = event.target.value;
    }

    handleGenerateClick() {
        this.isProcessing = true;
        this.showResult = false;
        this.error = null;

        // Appel à notre API middleware
        fetch('http://localhost:8000/generate_quote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': 'ITS2025'
            },
            body: JSON.stringify({
                prompt: this.prompt,
                draft_mode: false
            })
        })
        .then(response => response.json())
        .then(data => {
            this.isProcessing = false;
            if (data.status === 'error') {
                this.error = data.message;
                this.dispatchEvent(
                    new ShowToastEvent({
                        title: 'Erreur',
                        message: data.message,
                        variant: 'error'
                    })
                );
            } else {
                this.devisResult = data;
                this.showResult = true;
                
                // Vérifier s'il y a des alternatives à afficher
                this.showAlternatives = !data.all_products_available && Object.keys(data.alternatives || {}).length > 0;
                
                this.dispatchEvent(
                    new ShowToastEvent({
                        title: 'Succès',
                        message: `Devis ${data.quote_id} généré avec succès`,
                        variant: 'success'
                    })
                );
            }
        })
        .catch(error => {
            this.isProcessing = false;
            this.error = error.message;
            console.error('Erreur lors de la génération du devis', error);
            this.dispatchEvent(
                new ShowToastEvent({
                    title: 'Erreur',
                    message: 'Une erreur est survenue lors de la génération du devis',
                    variant: 'error'
                })
            );
        });
    }

    handleAlternativeSelection(event) {
        const productCode = event.target.dataset.productCode;
        const alternativeIndex = event.target.value;
        
        this.selectedAlternatives[productCode] = this.devisResult.alternatives[productCode][alternativeIndex];
    }

    handleUpdateDevis() {
        this.isProcessing = true;
        
        // Remplacer les produits indisponibles par les alternatives sélectionnées
        const updatedProducts = [...this.devisResult.products];
        
        for (const productCode in this.selectedAlternatives) {
            const alternative = this.selectedAlternatives[productCode];
            const index = updatedProducts.findIndex(p => p.code === productCode);
            
            if (index !== -1) {
                updatedProducts[index] = {
                    code: alternative.ItemCode,
                    name: alternative.ItemName,
                    quantity: updatedProducts[index].quantity,
                    unit_price: alternative.Price,
                    line_total: updatedProducts[index].quantity * alternative.Price
                };
            }
        }
        
        // Appel à notre API middleware pour mettre à jour le devis
        fetch('http://localhost:8000/update_quote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': 'ITS2025'
            },
            body: JSON.stringify({
                quote_id: this.devisResult.quote_id,
                products: updatedProducts
            })
        })
        .then(response => response.json())
        .then(data => {
            this.isProcessing = false;
            if (data.status === 'error') {
                this.error = data.message;
                this.dispatchEvent(
                    new ShowToastEvent({
                        title: 'Erreur',
                        message: data.message,
                        variant: 'error'
                    })
                );
            } else {
                this.devisResult = data;
                this.showAlternatives = false;
                
                this.dispatchEvent(
                    new ShowToastEvent({
                        title: 'Succès',
                        message: 'Devis mis à jour avec succès',
                        variant: 'success'
                    })
                );
            }
        })
        .catch(error => {
            this.isProcessing = false;
            this.error = error.message;
            console.error('Erreur lors de la mise à jour du devis', error);
            this.dispatchEvent(
                new ShowToastEvent({
                    title: 'Erreur',
                    message: 'Une erreur est survenue lors de la mise à jour du devis',
                    variant: 'error'
                })
            );
        });
    }
}