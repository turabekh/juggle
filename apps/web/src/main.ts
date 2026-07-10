import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { Quasar, Notify, Dialog, Loading } from 'quasar'

import '@quasar/extras/material-icons/material-icons.css'
import '@quasar/extras/material-icons-round/material-icons-round.css'
import 'quasar/src/css/index.sass'
import '@/css/app.scss'

import App from '@/App.vue'
import router from '@/router'

const app = createApp(App)

app.use(Quasar, {
  plugins: { Notify, Dialog, Loading },
  config: {
    notify: { position: 'top', timeout: 2600 },
  },
})
app.use(createPinia())
app.use(router)

app.mount('#app')
