import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import { FileTree } from './components/FileTree';
import { FileRecord } from './types';

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

  it('renders file tree component with sample data and handles selection', () => {
    const sampleFiles: FileRecord[] = [
      {
        id: 'f1-uuid',
        repository_id: 'r1-uuid',
        path: 'app/main.py',
        language: 'python',
        loc: 120,
        sha256: 'abc123sha',
        storage_key: 'repos/r1/files/app/main.py',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'f2-uuid',
        repository_id: 'r1-uuid',
        path: 'app/utils/math_ops.py',
        language: 'python',
        loc: 45,
        sha256: 'def456sha',
        storage_key: 'repos/r1/files/app/utils/math_ops.py',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ];

    const onSelectMock = vi.fn();

    render(
      <FileTree
        files={sampleFiles}
        selectedFileId="f1-uuid"
        onSelectFile={onSelectMock}
      />
    );

    // Verify header count
    expect(screen.getByText('Files (2)')).toBeInTheDocument();

    // Verify paths and LOC are rendered
    expect(screen.getByText('app/main.py')).toBeInTheDocument();
    expect(screen.getByText('120 L')).toBeInTheDocument();
    expect(screen.getByText('app/utils/math_ops.py')).toBeInTheDocument();
    expect(screen.getByText('45 L')).toBeInTheDocument();

    // Click on second file
    fireEvent.click(screen.getByText('app/utils/math_ops.py'));
    expect(onSelectMock).toHaveBeenCalledWith('f2-uuid');
  });
});
