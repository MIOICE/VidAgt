import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElButton,
  ElDialog,
  ElInput,
  ElOption,
  ElProgress,
  ElSelect,
  ElTabPane,
  ElTabs,
} from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/progress/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import 'element-plus/es/components/tabs/style/css'
import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)

for (const component of [
  ElButton,
  ElDialog,
  ElInput,
  ElOption,
  ElProgress,
  ElSelect,
  ElTabPane,
  ElTabs,
]) {
  app.use(component)
}

app.use(createPinia()).use(router).mount('#app')
