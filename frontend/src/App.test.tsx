import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import { FileTree } from './components/FileTree';
import { FunctionsTable } from './components/FunctionsTable';
import { RecommendationPanel } from './components/RecommendationPanel';
import { OptimizationPanel } from './components/OptimizationPanel';
import { api } from './api/client';
import { BottleneckRecord, FileRecord, Recommendation } from './types';

vi.mock('@monaco-editor/react', () => ({
  default: ({ value }: { value: string }) => <div data-testid="monaco-editor">{value}</div>,
  DiffEditor: ({ original, modified }: { original: string; modified: string }) => (
    <div data-testid="monaco-diff-editor">
      <div data-testid="diff-original">{original}</div>
      <div data-testid="diff-modified">{modified}</div>
    </div>
  ),
}));


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

  it('renders OptimizationPanel with mode selector and disabled LLM notice', async () => {
    vi.spyOn(api.optimizations, 'getConfig').mockResolvedValue({
      llm_provider: 'none',
      llm_enabled: false,
      llm_model: null,
      templates: ['T1_SET_MEMBERSHIP', 'T2_DICT_INDEX_JOIN'],
    });
    vi.spyOn(api.optimizations, 'list').mockResolvedValue([]);

    const mockBottleneck: BottleneckRecord = {
      id: 'b-opt-1',
      analysis_run_id: 'run-1',
      function_id: 'fn-1',
      static_score: 0.8,
      runtime_score: 0.7,
      call_count: 50,
      runtime_pct: 0.4,
      memory_peak_kb: 512,
      impact_score: 0.85,
      severity: 'CRITICAL',
      evidence: {
        recommendation: {
          current_algorithm: 'linear_scan',
          recommended_algorithm: 'hash_set',
          confidence: 0.95,
          reason: 'Set membership O(1)',
          source: 'rules',
        },
      },
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      function: {
        id: 'fn-1',
        file_id: 'f-1',
        repository_id: 'r-1',
        qualified_name: 'demo.operations.slow_membership',
        name: 'slow_membership',
        lineno: 10,
        end_lineno: 25,
        params: ['items', 'queries'],
        complexity_class: 'O(n^2)',
        complexity_rank: 4,
        loop_depth: 2,
        has_recursion: false,
        patterns: [{ pattern_id: 'LINEAR_MEMBERSHIP_IN_LOOP', line_number: 14, matched_snippet: 'if x in items:' }],
        severity: 'CRITICAL',
        metrics: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    };

    render(
      <OptimizationPanel
        bottleneck={mockBottleneck}
        originalSource="def slow_membership(items, queries):\n    res = []\n    for q in queries:\n        if q in items:\n            res.append(q)\n    return res"
        loadingSource={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Generate Candidate Optimization/i)).toBeInTheDocument();
      expect(screen.getByText(/Deterministic Template/i)).toBeInTheDocument();
      expect(screen.getByText(/LLM Synthesis/i)).toBeInTheDocument();
      expect(screen.getByText(/LLM disabled/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Generate Candidate/i })).toBeInTheDocument();
    });
  });

  it('renders OptimizationPanel with generated candidate diff and rationale', async () => {
    vi.spyOn(api.optimizations, 'getConfig').mockResolvedValue({
      llm_provider: 'none',
      llm_enabled: false,
      llm_model: null,
      templates: ['T1_SET_MEMBERSHIP'],
    });
    vi.spyOn(api.optimizations, 'list').mockResolvedValue([
      {
        id: 'opt-101',
        recommendation_id: 'rec-1',
        mode: 'template',
        template_id: 'T1_SET_MEMBERSHIP',
        candidate_code: 'def slow_membership(items, queries):\n    items_set = set(items)\n    return [q for q in queries if q in items_set]',
        patch: '--- original.py\n+++ candidate.py\n@@ -1,5 +1,3 @@',
        status: 'generated',
        decision_reason: {
          rationale: 'Converted linear list membership into O(1) set lookup.',
          safety_notes: 'Elements must be hashable.',
          changed_lines: [11, 12],
        },
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]);

    const mockBottleneck: BottleneckRecord = {
      id: 'b-opt-2',
      analysis_run_id: 'run-1',
      function_id: 'fn-1',
      static_score: 0.8,
      runtime_score: 0.7,
      call_count: 50,
      runtime_pct: 0.4,
      memory_peak_kb: 512,
      impact_score: 0.85,
      severity: 'CRITICAL',
      evidence: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    render(
      <OptimizationPanel
        bottleneck={mockBottleneck}
        originalSource="def slow_membership(items, queries):\n    res = []\n    for q in queries:\n        if q in items:\n            res.append(q)\n    return res"
        loadingSource={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Candidate Generated Successfully/i)).toBeInTheDocument();
      expect(screen.getByText(/Converted linear list membership into O\(1\) set lookup\./i)).toBeInTheDocument();
      expect(screen.getByText(/Elements must be hashable\./i)).toBeInTheDocument();
      expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument();
    });
  });
});
