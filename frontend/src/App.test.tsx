import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';

describe('Frontend Shell & Auth Flow', () => {
  it('renders login form and validates input fields', async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    );

    expect(screen.getByText(/sign in to algorevive ai/i)).toBeInTheDocument();
    const emailInput = screen.getByPlaceholderText('developer@example.com');
    const passwordInput = screen.getByPlaceholderText('••••••••');
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    expect(emailInput).toBeInTheDocument();
    expect(passwordInput).toBeInTheDocument();
    expect(submitButton).toBeInTheDocument();

    // Trigger submit with empty fields
    fireEvent.click(submitButton);

    await waitFor(() => {
      // Input is marked required
      expect(emailInput).toBeRequired();
      expect(passwordInput).toBeRequired();
    });
  });

  it('redirects unauthenticated users to /login on protected routes', async () => {
    localStorage.removeItem('algorevive_token');
    localStorage.removeItem('algorevive_user');

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login Page Target</div>} />
            <Route element={<ProtectedRoute />}>
              <Route path="/dashboard" element={<div>Protected Dashboard Content</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Login Page Target')).toBeInTheDocument();
      expect(screen.queryByText('Protected Dashboard Content')).not.toBeInTheDocument();
    });
  });
});
