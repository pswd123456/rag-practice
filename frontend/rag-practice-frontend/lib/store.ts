// lib/store.ts
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { ChatSession } from './types';
import { chatService } from './services/chat';

// === Auth Store ===
interface User {
  id: number;
  email: string;
  full_name?: string;
  is_active: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      login: (token, user) => set({ token, user, isAuthenticated: true }),
      logout: () => set({ token: null, user: null, isAuthenticated: false }),
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
);

// === Chat Store (New: Shared State for Sidebar and Pages) ===
interface ChatState {
  sessions: ChatSession[];
  isLoading: boolean;
  
  // Actions
  fetchSessions: () => Promise<void>;
  addSession: (session: ChatSession) => void;
  removeSession: (sessionId: string) => void;
  updateSessionInList: (sessionId: string, updates: Partial<ChatSession>) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  isLoading: false,

  fetchSessions: async () => {
    set({ isLoading: true });
    try {
      const data = await chatService.getSessions();
      set({ sessions: data });
    } catch (error) {
      console.error("Failed to fetch sessions:", error);
    } finally {
      set({ isLoading: false });
    }
  },

  addSession: (session) => {
    set((state) => ({ sessions: [session, ...state.sessions] }));
  },

  removeSession: (sessionId) => {
    set((state) => ({ 
      sessions: state.sessions.filter(s => s.id !== sessionId) 
    }));
  },

  updateSessionInList: (sessionId, updates) => {
    set((state) => ({
      sessions: state.sessions.map(s => 
        s.id === sessionId ? { ...s, ...updates } : s
      )
    }));
  }
}));