import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
    {
      path: '/videos/:id',
      name: 'workspace',
      component: () => import('./views/WorkspaceView.vue'),
    },
  ],
})
