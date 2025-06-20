<!doctype html>
<html>
  <head>
    <title>Eplumber Monitor</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.ico" />
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <link rel="stylesheet" href="/static/css/dashboard.css" />
  </head>
  <body>
    <div id="app">
      <h1>🔧 Eplumber Monitor</h1>
      
      <div class="controls">
        <a href="config.html" class="refresh-btn config-btn">⚙️ Config</a>
      </div>

      <div class="dashboard">
        <div class="panel">
          <h2>📊 Sensors</h2>
          <div
            v-for="sensor in sensors"
            :key="sensor.name"
            :class="['sensor', sensor.connected ? 'connected' : 'disconnected']"
          >
            <span class="sensor-name">{{ sensor.name }}</span>
            <span class="sensor-value">{{ sensor.mean !== null && sensor.mean !== undefined ? sensor.mean : 'N/A' }}</span>
          </div>
        </div>

        <div class="panel">
          <h2>⚡ Rules</h2>
          <div v-for="(rule, index) in rules" :key="index" :class="['rule', rule.all_tests_pass ? 'active' : '', !rule.active ? 'inactive' : '']">
            <div class="rule-name">
              {{ rule.action_name.split(' ⇒ ')[0] }}
              <span v-if="!rule.active" class="inactive-badge">INACTIVE</span>
            </div>
            <div
              v-for="test in rule.tests"
              :key="test.sensor_name"
              :class="['test', test.passes ? 'passing' : 'failing']"
            >
              <span>{{ test.sensor_name }}: {{ test.current_sensor_value }} {{ test.operator }} {{ test.value }}</span>
              <span class="test-emoji">{{ test.passes ? '✅' : '❌' }}</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <h2>📝 Actions</h2>
          <div v-for="action in actionHistory.slice(0, 10)" :key="action.timestamp" class="action">
            <strong>{{ action.timestamp.split(' ')[1] }}</strong> {{ action.name }}
          </div>
          <div v-if="actionHistory.length === 0" style="color: #6c757d; font-style: italic;">No actions yet</div>
        </div>
      </div>
    </div>

    <script>
      const { createApp } = Vue
      createApp({
        data() {
          return {
            sensors: [],
            actionHistory: [],
            rules: [],
          }
        },
        methods: {
          async fetchData() {
            try {
              const [sensorsRes, actionsRes, rulesRes] = await Promise.all([
                axios.get('/api/sensors'),
                axios.get('/api/actions/history'),
                axios.get('/api/rules'),
              ])
              this.sensors = sensorsRes.data.sensors
              this.actionHistory = actionsRes.data.actions
              this.rules = rulesRes.data.rules
            } catch (error) {
              console.error('Error fetching data:', error)
            }
          },
        },
        mounted() {
          this.fetchData()
          setInterval(this.fetchData, 5000) // Auto-refresh every 5 seconds
        },
      }).mount('#app')
    </script>
  </body>
</html>
