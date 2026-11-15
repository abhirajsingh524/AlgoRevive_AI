import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import { FileTree } from './components/FileTree';
import { FunctionsTable } from './components/FunctionsTable';
import { RecommendationPanel } from './components/RecommendationPanel';
import { BottleneckRecord, FileRecord, Recommendation } from './types';

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

  it('renders functions table with complexity badge, patterns and handles row selection', () => {
    const sampleFunctions = [
      {
        id: 'fn-1',
        file_id: 'f1-uuid',
        repository_id: 'r1-uuid',
        qualified_name: 'demo.operations.slow_membership',
        name: 'slow_membership',
        lineno: 10,
        end_lineno: 20,
        params: [],
        complexity_class: 'O(n^2)',
        complexity_rank: 4,
        loop_depth: 1,
        has_recursion: false,
        patterns: [
          {
            pattern_id: 'LINEAR_MEMBERSHIP_IN_LOOP',
            line_number: 14,
            matched_snippet: 'u["id"] in ids',
          },
        ],
        severity: 'HIGH',
        metrics: { loc: 10 },
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ];

    const onSelectFnMock = vi.fn();

    render(
      <FunctionsTable
        functions={sampleFunctions}
        onSelectFunction={onSelectFnMock}
      />
    );

    expect(screen.getByText('slow_membership')).toBeInTheDocument();
    expect(screen.getByText('demo.operations.slow_membership')).toBeInTheDocument();
    expect(screen.getByText('O(n^2)')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('LINEAR_MEMBERSHIP_IN_LOOP')).toBeInTheDocument();

    fireEvent.click(screen.getByText('slow_membership'));
    expect(onSelectFnMock).toHaveBeenCalledWith(sampleFunctions[0]);
  });

  it('renders RecommendationPanel with confidence, complexity, source badge, alternatives, and reason', () => {
    const mockBottleneck: BottleneckRecord = {
      id: 'b-1',
      analysis_run_id: 'run-1',
      function_id: 'fn-1',
      static_score: 0.67,
      runtime_score: 0.85,
      call_count: 500,
      runtime_pct: 0.9,
      memory_peak_kb: 250,
      impact_score: 0.8,
      severity: 'HIGH',
      evidence: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    const mockRecommendation: Recommendation = {
      id: 'rec-1',
      bottleneck_id: 'b-1',
      current_algorithm: 'linear_scan_membership',
      recommended_algorithm: 'hash_set',
      expected_complexity: 'O(n * m) -> O(n + m)',
      confidence: 0.85,
      alternatives: ['keep_current'],
      reason: 'Recommendation of hash_set is driven primarily by: Input Size (1,000 items, 38.5%).',
      source: 'ml',
      data_structure: {
        current_structure: 'list',
        recommended_structure: 'set',
        workload_reason: 'Workload exhibits high lookup frequency.',
      },
      feature_importance: [
        {
          feature: 'input_size_log10',
          display_name: 'Input Size (N)',
          importance: 0.385,
          value: 3.0,
          formatted_value: '1,000 items',
        },
        {
          feature: 'lookup_freq_level',
          display_name: 'Lookup Frequency',
          importance: 0.255,
          value: 2.0,
          formatted_value: 'HIGH',
        },
      ],
    };

    render(
      <RecommendationPanel
        bottleneck={mockBottleneck}
        recommendation={mockRecommendation}
      />
    );

    // Current and recommended algorithm
    expect(screen.getByText('linear_scan_membership')).toBeInTheDocument();
    expect(screen.getByText('hash_set')).toBeInTheDocument();

    // Source badge
    expect(screen.getByTestId('recommendation-source-badge')).toHaveTextContent(/SOURCE: ML/i);

    // Expected complexity
    expect(screen.getByText('O(n * m) -> O(n + m)')).toBeInTheDocument();

    // Confidence
    expect(screen.getByText('85%')).toBeInTheDocument();

    // Alternatives
    expect(screen.getByText('keep_current')).toBeInTheDocument();

    // Reason sentence
    expect(
      screen.getByText(/Recommendation of hash_set is driven primarily by/i)
    ).toBeInTheDocument();

    // Data structure section
    expect(screen.getByText('set')).toBeInTheDocument();
    expect(screen.getByText('Workload exhibits high lookup frequency.')).toBeInTheDocument();
  });

  it('renders rules fallback badge when source is rules', () => {
    const mockBottleneck: BottleneckRecord = {
      id: 'b-2',
      analysis_run_id: 'run-1',
      function_id: 'fn-2',
      static_score: 0.4,
      runtime_score: 0.4,
      call_count: 50,
      runtime_pct: 0.1,
      memory_peak_kb: 50,
      impact_score: 0.3,
      severity: 'MEDIUM',
      evidence: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    const mockRecommendation: Recommendation = {
      id: 'rec-2',
      bottleneck_id: 'b-2',
      current_algorithm: 'linear_scan_membership',
      recommended_algorithm: 'hash_set',
      expected_complexity: 'O(n * m) -> O(n + m)',
      confidence: 0.95,
      alternatives: ['keep_current'],
      reason: 'Rule-based optimization applied.',
      source: 'rules',
    };

    render(
      <RecommendationPanel
        bottleneck={mockBottleneck}
        recommendation={mockRecommendation}
      />
    );

    expect(screen.getByTestId('recommendation-source-badge')).toHaveTextContent(/SOURCE: RULES/i);
  });

  it('renders placeholder when no recommendation is available', () => {
    const mockBottleneck: BottleneckRecord = {
      id: 'b-3',
      analysis_run_id: 'run-1',
      function_id: 'fn-3',
      static_score: 0.1,
      runtime_score: 0.1,
      call_count: 5,
      runtime_pct: 0.01,
      memory_peak_kb: 10,
      impact_score: 0.1,
      severity: 'LOW',
      evidence: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    render(
      <RecommendationPanel
        bottleneck={mockBottleneck}
        recommendation={null}
      />
    );

    expect(screen.getByText('No Recommendation Available')).toBeInTheDocument();
  });
});
