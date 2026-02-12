import React, { useState, useEffect } from 'react';
import axios from 'axios';

// Types
interface PendingProduct {
  external_code: string;
  external_description: string;
  supplier_card_code: string;
  supplier_name?: string;
  matched_item_code?: string;
  match_method?: string;
  confidence_score: number;
  status: string;
  created_at: string;
  use_count: number;
}

interface Statistics {
  total: number;
  validated: number;
  pending: number;
  exact_matches: number;
  fuzzy_matches: number;
  manual_matches: number;
}

interface SearchResult {
  item_code: string;
  item_name: string;
  item_group: string;
}

const API_BASE = 'http://localhost:8001';

export default function ProductValidation() {
  const [products, setProducts] = useState<PendingProduct[]>([]);
  const [stats, setStats] = useState<Statistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedProduct, setSelectedProduct] = useState<PendingProduct | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);

  // Form state
  const [formData, setFormData] = useState({
    item_code: '',
    item_name: '',
    item_group: '100',
    purchase_item: true,
    sales_item: true,
    inventory_item: true
  });

  // Load data
  useEffect(() => {
    loadPendingProducts();
    loadStatistics();
  }, []);

  const loadPendingProducts = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/products/pending?limit=100`);
      setProducts(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Erreur chargement produits:', error);
      setLoading(false);
    }
  };

  const loadStatistics = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/products/mapping/statistics`);
      setStats(response.data);
    } catch (error) {
      console.error('Erreur chargement stats:', error);
    }
  };

  const searchSAPProducts = async (query: string) => {
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }

    try {
      const response = await axios.get(`${API_BASE}/api/products/search`, {
        params: { query, limit: 10 }
      });
      setSearchResults(response.data);
    } catch (error) {
      console.error('Erreur recherche:', error);
    }
  };

  const handleAssociate = async (sapProduct: SearchResult) => {
    if (!selectedProduct) return;

    try {
      await axios.post(`${API_BASE}/api/products/validate`, {
        external_code: selectedProduct.external_code,
        supplier_card_code: selectedProduct.supplier_card_code,
        matched_item_code: sapProduct.item_code
      });

      alert(`✅ Produit associé: ${selectedProduct.external_code} → ${sapProduct.item_code}`);
      setSelectedProduct(null);
      loadPendingProducts();
      loadStatistics();
    } catch (error) {
      alert('❌ Erreur association: ' + error);
    }
  };

  const handleCreateProduct = async () => {
    if (!selectedProduct) return;

    try {
      const response = await axios.post(`${API_BASE}/api/products/create`, {
        external_code: selectedProduct.external_code,
        external_description: selectedProduct.external_description,
        supplier_card_code: selectedProduct.supplier_card_code,
        new_item_code: formData.item_code || undefined,
        item_name: formData.item_name,
        item_group: formData.item_group,
        purchase_item: formData.purchase_item,
        sales_item: formData.sales_item,
        inventory_item: formData.inventory_item
      });

      alert(`✅ Produit créé dans SAP: ${response.data.item_code}`);
      setShowCreateForm(false);
      setSelectedProduct(null);
      loadPendingProducts();
      loadStatistics();
    } catch (error: any) {
      alert('❌ Erreur création: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleReject = async (product: PendingProduct) => {
    if (!confirm(`Supprimer le produit ${product.external_code}?`)) return;

    try {
      await axios.delete(
        `${API_BASE}/api/products/mapping/${product.external_code}`,
        { params: { supplier_card_code: product.supplier_card_code } }
      );

      alert('✅ Produit supprimé');
      loadPendingProducts();
      loadStatistics();
    } catch (error) {
      alert('❌ Erreur suppression: ' + error);
    }
  };

  const generateItemCode = (externalCode: string) => {
    const clean = externalCode.replace(/-/g, '').toUpperCase();
    return `RONDOT-${clean}`.substring(0, 20);
  };

  const openCreateForm = (product: PendingProduct) => {
    setSelectedProduct(product);
    setShowCreateForm(true);
    setFormData({
      item_code: generateItemCode(product.external_code),
      item_name: product.external_description || `Article ${product.external_code}`,
      item_group: '100',
      purchase_item: true,
      sales_item: true,
      inventory_item: true
    });
  };

  if (loading) {
    return <div className="p-8 text-center">Chargement...</div>;
  }

  return (
    <div className="container mx-auto p-6 max-w-7xl">
      <h1 className="text-3xl font-bold mb-6">Validation Produits Externes</h1>

      {/* STATISTIQUES */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="text-3xl font-bold text-blue-600">{stats.pending}</div>
            <div className="text-sm text-gray-600">En attente</div>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <div className="text-3xl font-bold text-green-600">{stats.validated}</div>
            <div className="text-sm text-gray-600">Validés</div>
          </div>
          <div className="bg-gray-50 p-4 rounded-lg">
            <div className="text-3xl font-bold text-gray-600">{stats.total}</div>
            <div className="text-sm text-gray-600">Total</div>
          </div>
        </div>
      )}

      {/* LISTE PRODUITS */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="bg-gray-50 px-6 py-3 border-b">
          <h2 className="text-lg font-semibold">
            Produits en attente de validation ({products.length})
          </h2>
        </div>

        {products.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            ✅ Aucun produit en attente
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Code Externe</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Fournisseur</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {products.map((product) => (
                  <tr key={`${product.external_code}-${product.supplier_card_code}`} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-sm">{product.external_code}</td>
                    <td className="px-4 py-3 text-sm">{product.external_description || '-'}</td>
                    <td className="px-4 py-3 text-sm">{product.supplier_card_code}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(product.created_at).toLocaleDateString('fr-FR')}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => setSelectedProduct(product)}
                          className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
                        >
                          Associer
                        </button>
                        <button
                          onClick={() => openCreateForm(product)}
                          className="px-3 py-1 text-sm bg-green-500 text-white rounded hover:bg-green-600"
                        >
                          Créer
                        </button>
                        <button
                          onClick={() => handleReject(product)}
                          className="px-3 py-1 text-sm bg-red-500 text-white rounded hover:bg-red-600"
                        >
                          Rejeter
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* MODAL ASSOCIATION */}
      {selectedProduct && !showCreateForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <h3 className="text-xl font-bold mb-4">Associer à un produit SAP existant</h3>

            <div className="mb-4 p-4 bg-gray-50 rounded">
              <div className="font-semibold">{selectedProduct.external_code}</div>
              <div className="text-sm text-gray-600">{selectedProduct.external_description}</div>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Rechercher un produit SAP</label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  searchSAPProducts(e.target.value);
                }}
                className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500"
                placeholder="Code ou nom du produit..."
              />
            </div>

            {searchResults.length > 0 && (
              <div className="mb-4">
                <div className="text-sm font-medium mb-2">{searchResults.length} résultat(s)</div>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {searchResults.map((result) => (
                    <div
                      key={result.item_code}
                      onClick={() => handleAssociate(result)}
                      className="p-3 border rounded hover:bg-blue-50 cursor-pointer"
                    >
                      <div className="font-mono text-sm font-semibold">{result.item_code}</div>
                      <div className="text-sm text-gray-600">{result.item_name}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setSelectedProduct(null)}
                className="flex-1 px-4 py-2 bg-gray-200 rounded hover:bg-gray-300"
              >
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL CRÉATION */}
      {showCreateForm && selectedProduct && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full">
            <h3 className="text-xl font-bold mb-4">Créer un nouveau produit dans SAP</h3>

            <div className="mb-4 p-4 bg-gray-50 rounded">
              <div className="text-sm text-gray-600">Code externe</div>
              <div className="font-semibold">{selectedProduct.external_code}</div>
              <div className="text-sm text-gray-600 mt-2">Description externe</div>
              <div className="font-semibold">{selectedProduct.external_description}</div>
            </div>

            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium mb-1">Code SAP (ItemCode)</label>
                <input
                  type="text"
                  value={formData.item_code}
                  onChange={(e) => setFormData({ ...formData, item_code: e.target.value })}
                  className="w-full px-3 py-2 border rounded"
                  maxLength={20}
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Nom produit (ItemName)</label>
                <input
                  type="text"
                  value={formData.item_name}
                  onChange={(e) => setFormData({ ...formData, item_name: e.target.value })}
                  className="w-full px-3 py-2 border rounded"
                  maxLength={100}
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Groupe produits</label>
                <select
                  value={formData.item_group}
                  onChange={(e) => setFormData({ ...formData, item_group: e.target.value })}
                  className="w-full px-3 py-2 border rounded"
                >
                  <option value="100">100 - Produits généraux</option>
                  <option value="105">105 - Pièces détachées</option>
                  <option value="110">110 - Matières premières</option>
                </select>
              </div>

              <div className="flex gap-4">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.purchase_item}
                    onChange={(e) => setFormData({ ...formData, purchase_item: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Article achetable</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.sales_item}
                    onChange={(e) => setFormData({ ...formData, sales_item: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Article vendable</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.inventory_item}
                    onChange={(e) => setFormData({ ...formData, inventory_item: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Article stockable</span>
                </label>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowCreateForm(false)}
                className="flex-1 px-4 py-2 bg-gray-200 rounded hover:bg-gray-300"
              >
                Annuler
              </button>
              <button
                onClick={handleCreateProduct}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
              >
                Créer dans SAP
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
