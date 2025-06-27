<!doctype html>
<html>
  <head>
    <title>Eplumber Config Editor</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.ico" />
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <link rel="stylesheet" href="/static/css/main.css" />
  </head>
  <body>
    <div id="app" class="config-editor">
      <div class="header-container">
        <div class="logo-container"><img src="/logo.svg" alt="Eplumber Logo" class="logo" />🔧</div>

        <div class="controls">
          <div class="nav-buttons">
            <a href="/">← Dashboard</a>
          </div>
        </div>
      </div>

      <div
        v-if="statusMessage"
        :class="['status-message', statusType === 'success' ? 'status-success' : 'status-error']"
      >
        {{ statusMessage }}
      </div>

      <div v-if="validationErrors.length > 0" class="validation-errors">
        <strong>Validation Errors:</strong>
        <ul>
          <li v-for="error in validationErrors" :key="error">{{ error }}</li>
        </ul>
      </div>

      <!-- MQTT Settings -->
      <div class="form-section">
        <h2>📡 MQTT Settings</h2>
        <div class="form-row">
          <div class="form-group">
            <label>Host</label>
            <input v-model="config.mqtt.host" class="form-control" type="text" placeholder="mqtt.example.com" />
          </div>
          <div class="form-group">
            <label>Port</label>
            <input v-model.number="config.mqtt.port" class="form-control" type="number" placeholder="1883" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Username</label>
            <input v-model="config.mqtt.username" class="form-control" type="text" placeholder="mqtt_user" />
          </div>
          <div class="form-group">
            <label>Password</label>
            <input v-model="config.mqtt.password" class="form-control" type="password" placeholder="mqtt_password" />
          </div>
        </div>
      </div>

      <!-- Sensors -->
      <div class="form-section">
        <h2>📊 Sensors</h2>
        <div v-for="(sensor, index) in config.sensors" :key="index" class="list-item">
          <div class="list-item-header">
            <span class="list-item-title">Sensor {{ index + 1 }}: {{ sensor.name || 'Unnamed' }}</span>
            <button @click="removeSensor(index)" class="btn-remove">Remove</button>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Name</label>
              <input v-model="sensor.name" class="form-control" type="text" placeholder="sensor_name" />
            </div>
            <div class="form-group">
              <label>Type</label>
              <select v-model="sensor.type" class="form-control">
                <option value="mqtt">MQTT</option>
                <option value="http">HTTP</option>
                <option value="time">Time</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Route</label>
              <input
                v-model="sensor.route"
                class="form-control"
                type="text"
                :placeholder="
                  sensor.type === 'mqtt'
                    ? 'emon/device/topic'
                    : sensor.type === 'http'
                    ? 'http://device/api/status'
                    : 'Auto-generated'
                "
              />
            </div>
            <div class="form-group">
              <label>Return Type</label>
              <select v-model="sensor.return_type" class="form-control">
                <option value="float">Float</option>
                <option value="int">Integer</option>
                <option value="str">String</option>
                <option value="bool">Boolean</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>Value List Length</label>
            <input
              v-model.number="sensor.value_list_length"
              class="form-control"
              type="number"
              min="1"
              max="100"
              placeholder="5"
            />
          </div>
          <div v-if="sensor.type === 'http'" class="form-group">
            <label>JSON Path (optional)</label>
            <input v-model="sensor.json_path" class="form-control" type="text" placeholder="'switch:0'.output" />
          </div>
          <div v-if="sensor.comment" class="form-group">
            <label>Comment</label>
            <input v-model="sensor.comment" class="form-control" type="text" placeholder="Sensor description" />
          </div>
        </div>
        <button @click="addSensor" class="btn-add">+ Add Sensor</button>
      </div>

      <!-- Actions -->
      <div class="form-section">
        <h2>⚡ Actions</h2>
        <div v-for="(action, index) in config.actions" :key="index" class="list-item">
          <div class="list-item-header">
            <span class="list-item-title">Action {{ index + 1 }}: {{ action.name || 'Unnamed' }}</span>
            <button @click="removeAction(index)" class="btn-remove">Remove</button>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Name</label>
              <input v-model="action.name" class="form-control" type="text" placeholder="action_name" />
            </div>
            <div class="form-group">
              <label>HTTP Route</label>
              <input
                v-model="action.route"
                class="form-control"
                type="text"
                placeholder="http://device/relay/0?turn=on"
              />
            </div>
          </div>
        </div>
        <button @click="addAction" class="btn-add">+ Add Action</button>
      </div>

      <!-- Rules -->
      <div class="form-section">
        <h2>📋 Rules</h2>
        <div v-for="(rule, ruleIndex) in config.rules" :key="ruleIndex" class="list-item">
          <div class="list-item-header">
            <span class="list-item-title">Rule {{ ruleIndex + 1 }}: {{ rule.name || 'Unnamed' }}</span>
            <button @click="removeRule(ruleIndex)" class="btn-remove">Remove</button>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Rule Name</label>
              <input v-model="rule.name" class="form-control" type="text" placeholder="rule_name" />
            </div>
            <div class="form-group">
              <label>Action</label>
              <select v-model="rule.action" class="form-control">
                <option value="">Select Action</option>
                <option v-for="action in config.actions" :key="action.name" :value="action.name">
                  {{ action.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label style="display: flex; align-items: center; gap: 10px">
                <input type="checkbox" v-model="rule.active" style="margin: 0; width: auto; height: auto" />
                Active
              </label>
            </div>
          </div>

          <div style="margin-top: 15px">
            <label style="font-weight: bold">Tests (All must pass for rule to trigger)</label>
            <div v-for="(test, testIndex) in rule.tests" :key="testIndex" class="test-item">
              <div class="test-row">
                <select v-model="test[0]" class="form-control">
                  <option value="">Select Sensor</option>
                  <option v-for="sensor in config.sensors" :key="sensor.name" :value="sensor.name">
                    {{ sensor.name }}
                  </option>
                  <option value="time">time</option>
                </select>
                <select v-model="test[1]" class="form-control">
                  <option value="<"><</option>
                  <option value="<="><=</option>
                  <option value=">">></option>
                  <option value=">=">>=</option>
                  <option value="==">=</option>
                  <option value="!=">!=</option>
                </select>
                <input
                  v-model="test[2]"
                  class="form-control"
                  type="text"
                  placeholder="Value (number, string, or boolean)"
                />
                <button @click="removeTest(ruleIndex, testIndex)" class="btn-remove-small">×</button>
              </div>
            </div>
            <button
              @click="addTest(ruleIndex)"
              class="btn-add"
              style="margin-top: 8px; padding: 5px 10px; font-size: 12px"
            >
              + Add Test
            </button>
          </div>
        </div>
        <button @click="addRule" class="btn-add">+ Add Rule</button>
      </div>

      <div class="form-section">
        <button @click="saveConfig" :disabled="loading" class="btn btn-primary">
          {{ loading ? 'Saving...' : 'Save & Restart' }}
        </button>
      </div>
    </div>

    <script>
      const { createApp } = Vue
      createApp({
        data() {
          return {
            config: {
              mqtt: {
                host: '',
                port: 1883,
                username: '',
                password: '',
              },
              sensors: [],
              actions: [],
              rules: [],
            },
            loading: false,
            statusMessage: '',
            statusType: 'success',
            validationErrors: [],
          }
        },
        methods: {
          async loadConfig() {
            this.loading = true
            this.clearStatus()
            try {
              const response = await axios.get('/api/config')
              this.config = response.data.config
              if (this.config.rules) {
                this.config.rules.forEach((rule) => {
                  if (rule.active === undefined || rule.active === null) {
                    rule.active = true
                  }
                })
              }
              this.showStatus('Configuration loaded successfully', 'success')
            } catch (error) {
              this.showStatus(`Error loading config: ${error.response?.data?.error || error.message}`, 'error')
            } finally {
              this.loading = false
            }
          },

          async saveConfig() {
            this.loading = true
            this.clearStatus()
            this.validationErrors = []

            try {
              const response = await axios.put('/api/config', {
                config: this.config,
              })
              this.showStatus('Configuration saved and applied successfully!', 'success')
            } catch (error) {
              if (error.response?.data?.error) {
                this.showStatus(`Error: ${error.response.data.error}`, 'error')
              } else {
                this.showStatus(`Error saving config: ${error.message}`, 'error')
              }
            } finally {
              this.loading = false
            }
          },

          addSensor() {
            this.config.sensors.push({
              name: '',
              route: '',
              type: 'mqtt',
              return_type: 'float',
              value_list_length: 5,
            })
          },

          removeSensor(index) {
            this.config.sensors.splice(index, 1)
          },

          addAction() {
            this.config.actions.push({
              name: '',
              route: '',
            })
          },

          removeAction(index) {
            this.config.actions.splice(index, 1)
          },

          addRule() {
            this.config.rules.push({
              name: '',
              tests: [['', '>', '']],
              action: '',
              active: true,
            })
          },

          removeRule(index) {
            this.config.rules.splice(index, 1)
          },

          addTest(ruleIndex) {
            this.config.rules[ruleIndex].tests.push(['', '>', ''])
          },

          removeTest(ruleIndex, testIndex) {
            this.config.rules[ruleIndex].tests.splice(testIndex, 1)
          },

          showStatus(message, type) {
            this.statusMessage = message
            this.statusType = type
            setTimeout(() => {
              this.clearStatus()
            }, 5000)
          },

          clearStatus() {
            this.statusMessage = ''
            this.validationErrors = []
          },
        },

        mounted() {
          this.loadConfig()
        },
      }).mount('#app')
    </script>
  </body>
</html>
