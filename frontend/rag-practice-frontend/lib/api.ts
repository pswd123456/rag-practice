// lib/api.ts
import axios from 'axios';
import { useAuthStore } from '@/lib/store';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

// 1. 请求拦截器：自动附加 Token
api.interceptors.request.use(
  (config) => {
    // 注意：在组件外部使用 Zustand 的 getState 方法
    const token = useAuthStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 2. 响应拦截器：统一错误处理
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // 处理 401 Unauthorized
    if (error.response?.status === 401) {
      // 清除状态并跳转 (在客户端组件中通常由路由守卫处理，这里清理数据)
      useAuthStore.getState().logout();
      // 可选：强制重定向
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;