/** Mirrors backend/app/models/user.py's response/request shapes for `/api/v1/auth/*`. */

export interface UserPublic {
  id: string;
  email: string;
  name: string | null;
  createdAt: string;
}

export interface AuthCredentials {
  email: string;
  password: string;
}

/** Request body for PATCH /api/v1/auth/me -- name is the only editable field. */
export interface UserUpdateInput {
  name: string | null;
}

export interface Token {
  accessToken: string;
  tokenType: string;
}
