<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.availableBudget') }}</div>
          <div class="stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ formatCurrency(totalCost, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ formatCurrency(remainingBudget, currentCurrency) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.availableBudget') }}</h3>
        </div>
        <div class="budget-slider">
          <input
            type="range"
            :min="0"
            :max="maxBudget"
            :step="500"
            v-model.number="budget"
            @input="onBudgetInput"
            class="budget-range"
          />
          <div class="budget-readout">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ recommendations.length }})</h3>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <template v-else>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>{{ t('restocking.table.sku') }}</th>
                  <th>{{ t('restocking.table.item') }}</th>
                  <th>{{ t('restocking.table.category') }}</th>
                  <th>{{ t('restocking.table.currentDemand') }}</th>
                  <th>{{ t('restocking.table.forecastedDemand') }}</th>
                  <th>{{ t('restocking.table.gap') }}</th>
                  <th>{{ t('restocking.table.quantity') }}</th>
                  <th>{{ t('restocking.table.unitCost') }}</th>
                  <th>{{ t('restocking.table.lineTotal') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in recommendations" :key="item.sku">
                  <td><strong>{{ item.sku }}</strong></td>
                  <td>{{ translateProductName(item.name) }}</td>
                  <td>{{ translateCategory(item.category) }}</td>
                  <td>{{ item.current_demand }}</td>
                  <td>{{ item.forecasted_demand }}</td>
                  <td><strong>{{ item.gap }}</strong></td>
                  <td>{{ item.gap }}</td>
                  <td>{{ formatCurrency(item.unit_cost, currentCurrency) }}</td>
                  <td>{{ formatCurrency(item.line_total, currentCurrency) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="skippedCount > 0" class="skipped-note">
            {{ t('restocking.skippedItems', { count: skippedCount }) }}
          </p>
        </template>

        <div v-if="submitSuccess" class="success-banner">
          {{ t('restocking.orderPlaced', {
            orderNumber: submitSuccess.order_number,
            date: formatDate(submitSuccess.expected_delivery),
            days: submitSuccess.lead_days
          }) }}
        </div>
        <div v-if="submitError" class="error">{{ submitError }}</div>

        <button
          class="place-order-btn"
          :disabled="!canPlaceOrder"
          @click="placeOrder"
        >
          {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName, currentLocale } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const inventory = ref([])

    const budget = ref(5000)
    const budgetTouched = ref(false)

    const submitting = ref(false)
    const submitError = ref(null)
    const submitSuccess = ref(null)

    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    const candidates = computed(() => {
      const invBySku = new Map(inventory.value.map(item => [item.sku, item]))
      const result = []

      for (const f of forecasts.value) {
        const inv = invBySku.get(f.item_sku)
        if (!inv) continue
        const gap = f.forecasted_demand - f.current_demand
        if (gap <= 0) continue

        result.push({
          sku: f.item_sku,
          name: inv.name,
          category: inv.category,
          current_demand: f.current_demand,
          forecasted_demand: f.forecasted_demand,
          gap,
          unit_cost: inv.unit_cost,
          line_total: gap * inv.unit_cost
        })
      }

      result.sort((a, b) => {
        if (b.gap !== a.gap) return b.gap - a.gap
        return a.line_total - b.line_total
      })

      return result
    })

    const maxBudget = computed(() => {
      const totalOfAll = candidates.value.reduce((sum, c) => sum + c.line_total, 0)
      return Math.max(5000, Math.ceil(totalOfAll / 5000) * 5000)
    })

    const recommendations = computed(() => {
      let remaining = budget.value
      const picked = []

      for (const item of candidates.value) {
        if (item.line_total <= remaining + 0.001) {
          picked.push(item)
          remaining -= item.line_total
        }
      }

      return picked
    })

    const totalCost = computed(() => {
      return recommendations.value.reduce((sum, item) => sum + item.line_total, 0)
    })

    const remainingBudget = computed(() => budget.value - totalCost.value)
    const skippedCount = computed(() => candidates.value.length - recommendations.value.length)
    const canPlaceOrder = computed(() => recommendations.value.length > 0 && !submitting.value)

    watch(maxBudget, (newMax) => {
      if (!budgetTouched.value) {
        budget.value = Math.round(newMax * 0.5 / 500) * 500
      }
    })

    const onBudgetInput = () => {
      budgetTouched.value = true
      submitSuccess.value = null
    }

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null
        const filters = getCurrentFilters()

        const [forecastsData, inventoryData] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory({
            warehouse: filters.warehouse,
            category: filters.category
          })
        ])

        forecasts.value = forecastsData
        inventory.value = inventoryData
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    watch([selectedLocation, selectedCategory], () => {
      loadData()
    })

    const translateCategory = (category) => {
      const categoryMap = {
        'Circuit Boards': t('categories.circuitBoards'),
        'Sensors': t('categories.sensors'),
        'Actuators': t('categories.actuators'),
        'Controllers': t('categories.controllers'),
        'Power Supplies': t('categories.powerSupplies')
      }
      return categoryMap[category] || category
    }

    const formatDate = (dateString) => {
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString
      return date.toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    const placeOrder = async () => {
      submitting.value = true
      submitError.value = null
      try {
        const order = await api.createRestockOrder({
          budget: budget.value,
          items: recommendations.value.map(r => ({ sku: r.sku, quantity: r.gap }))
        })
        submitSuccess.value = order
      } catch (err) {
        submitError.value = t('restocking.submitError')
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      t,
      currentCurrency,
      translateProductName,
      translateCategory,
      formatCurrency,
      loading,
      error,
      budget,
      candidates,
      maxBudget,
      recommendations,
      totalCost,
      remainingBudget,
      skippedCount,
      canPlaceOrder,
      onBudgetInput,
      submitting,
      submitError,
      submitSuccess,
      formatDate,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-slider {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.5rem 0;
}

.budget-range {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
}

.budget-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 3px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.budget-range::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 3px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.budget-readout {
  min-width: 120px;
  text-align: right;
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.skipped-note {
  margin-top: 0.75rem;
  color: #94a3b8;
  font-size: 0.813rem;
  font-style: italic;
}

.success-banner {
  margin-top: 1rem;
  padding: 0.875rem 1rem;
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  border-radius: 8px;
  font-size: 0.938rem;
}

.place-order-btn {
  margin-top: 1rem;
  padding: 0.75rem 1.75rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
