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
      <div style="margin-bottom: 20px">
        <button @click="fetchData" class="refresh-btn">🔄 Refresh</button>
        <a href="config.html" class="refresh-btn" style="text-decoration: none; display: inline-block"
          >⚙️ Edit Config</a
        >
      </div>

      <div class="dashboard">
        <div class="panel">
          <h2>📊 Sensors</h2>
          <div
            v-for="sensor in sensors"
            :key="sensor.name"
            :class="['sensor', sensor.connected ? 'connected' : 'disconnected']"
          >
            <strong>{{ sensor.name }}</strong> ({{ sensor.type }}) <br />Route: {{ sensor.route }} <br />Current:
            <strong>{{ sensor.mean !== null && sensor.mean !== undefined ? sensor.mean : 'N/A' }}</strong>
            <br />Values: {{ sensor.value_count }}/10 <br />Status:
          </div>
        </div>

        <div class="panel">
          <h2>⚡ Rules Status</h2>
          <div v-for="(rule, index) in rules" :key="index" :class="['rule', rule.all_tests_pass ? 'active' : '']">
            <strong>{{ rule.action_name }}</strong>
            <div
              v-for="test in rule.tests"
              :key="test.sensor_name"
              :class="['test', test.passes ? 'passing' : 'failing']"
            >
              {{ test.sensor_name }} {{ test.operator }} {{ test.value }} (current: {{ test.current_sensor_value }})
              {{ test.passes ? '✅' : '❌' }}
            </div>
          </div>
        </div>

        <div class="panel">
          <h2>📝 Action History</h2>
          <div v-for="action in actionHistory" :key="action.timestamp" class="action">
            <strong>{{ action.timestamp }}</strong> - {{ action.name }} <br /><small>{{ action.route }}</small>
          </div>
          <div v-if="actionHistory.length === 0">No actions executed yet</div>
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
