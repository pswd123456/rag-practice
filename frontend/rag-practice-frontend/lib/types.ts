// lib/types.ts

// 对应后端 app/domain/schemas/token.py
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// 对应后端 app/domain/schemas/user.py (UserRead)
export interface UserRead {
  id: number;
  email: string;
  full_name?: string;
  is_active: boolean;
}