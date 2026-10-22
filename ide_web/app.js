/**
 * UnitLang Web IDE Client Application
 */

// Application State
const state = {
  samples: [],
  activeSampleId: null,
  activeSample: null,
  originalCode: "",
  isDirty: false,
  tacViewMode: "opt", // 'opt', 'unopt', 'diff'
  lastRunResult: null,
  testSuiteResults: null,
};

// DOM Elements
const el = {
  // Navigation & Controls
  engineSelect: document.getElementById("engine-select"),
  optToggle: document.getElementById("opt-toggle"),
  runBtn: document.getElementById("run-btn"),
  testAllBtn: document.getElementById("test-all-btn"),
  saveBtn: document.getElementById("save-btn"),
  activeFilename: document.getElementById("active-filename"),
  dirtyIndicator: document.getElementById("dirty-indicator"),
  
  // Sidebar
  sampleList: document.getElementById("sample-list"),
  sampleSearch: document.getElementById("sample-search"),
  totalSamplesCount: document.getElementById("total-samples-count"),
  newScratchpadBtn: document.getElementById("new-scratchpad-btn"),
  
  // Editor
  codeEditor: document.getElementById("code-editor"),
  lineNumbers: document.getElementById("line-numbers"),
  currentTitle: document.getElementById("current-title"),
  currentDesc: document.getElementById("current-desc"),
  formatBtn: document.getElementById("format-btn"),
  copyCodeBtn: document.getElementById("copy-code-btn"),
  statusCursor: document.getElementById("status-cursor"),
  statusLines: document.getElementById("status-lines"),
  
  // Tabs
  tabBtns: document.querySelectorAll(".tab-btn"),
  tabPanes: document.querySelectorAll(".tab-pane"),
  testStatusPill: document.getElementById("test-status-pill"),
  
  // Terminal Tab
  terminalOutput: document.getElementById("terminal-output"),
  termExecTime: document.getElementById("term-exec-time"),
  clearTermBtn: document.getElementById("clear-term-btn"),
  
  // Comparison Tab
  comparisonBanner: document.getElementById("comparison-banner"),
  bannerStatusIcon: document.getElementById("banner-status-icon"),
  bannerTitle: document.getElementById("banner-title"),
  bannerSubtitle: document.getElementById("banner-subtitle"),
  actualStatusBadge: document.getElementById("actual-status-badge"),
  actualExitCode: document.getElementById("actual-exit-code"),
  actualStdout: document.getElementById("actual-stdout"),
  actualStderr: document.getElementById("actual-stderr"),
  expectedSpecBadge: document.getElementById("expected-spec-badge"),
  expectedExitCode: document.getElementById("expected-exit-code"),
  expectedStdout: document.getElementById("expected-stdout"),
  expectedStderr: document.getElementById("expected-stderr"),
  diffMismatchBox: document.getElementById("diff-mismatch-box"),
  mismatchList: document.getElementById("mismatch-list"),
  
  // TAC Tab
  irOutput: document.getElementById("ir-output"),
  irViewOpt: document.getElementById("ir-view-opt"),
  irViewUnopt: document.getElementById("ir-view-unopt"),
  irViewDiff: document.getElementById("ir-view-diff"),
  
  // Bytecode Tab
  bytecodeOutput: document.getElementById("bytecode-output"),
  
  // Symbols Tab
  unitsTableBody: document.querySelector("#units-table tbody"),
  globalsTableBody: document.querySelector("#globals-table tbody"),
  functionsTableBody: document.querySelector("#functions-table tbody"),
  
  // Stats Tab
  statTacReduction: document.getElementById("stat-tac-reduction"),
  statFolded: document.getElementById("stat-folded"),
  statUnitFolds: document.getElementById("stat-unit-folds"),
  statConstantsPropagated: document.getElementById("stat-constants-propagated"),
  statDeadCode: document.getElementById("stat-dead-code"),
  statBytecodeReduction: document.getElementById("stat-bytecode-reduction"),
  statPeephole: document.getElementById("stat-peephole"),
  statVmSteps: document.getElementById("stat-vm-steps"),
  
  // Test Runner Tab
  startTestSuiteBtn: document.getElementById("start-test-suite-btn"),
  runnerBigStatus: document.getElementById("runner-big-status"),
  runnerSummaryText: document.getElementById("runner-summary-text"),
  progressContainer: document.getElementById("progress-container"),
  progressBarFill: document.getElementById("progress-bar-fill"),
  progressText: document.getElementById("progress-text"),
  progressPercent: document.getElementById("progress-percent"),
  filterAllCount: document.getElementById("filter-all-count"),
  filterPassCount: document.getElementById("filter-pass-count"),
  filterFailCount: document.getElementById("filter-fail-count"),
  testResultsBody: document.getElementById("test-results-body"),
  filterChips: document.querySelectorAll(".filter-chip"),
};

// ============================================================================
// Initialization
// ============================================================================
async function init() {
  setupEventListeners();
  setupEditor();
  await loadSamples();

  // Load first sample (01_basics.ul)
  const defaultSample = state.samples.find(s => s.id === "examples/01_basics.ul") || state.samples[0];
  if (defaultSample) {
    selectSample(defaultSample.id);
  }
}

// ============================================================================
// Sample Loading & Rendering
// ============================================================================
async function loadSamples() {
  try {
    const res = await fetch("/api/samples");
    state.samples = await res.json();
    el.totalSamplesCount.textContent = state.samples.length;
    renderSampleList();
  } catch (err) {
    console.error("Failed to load samples:", err);
    el.sampleList.innerHTML = `<div class="empty-row">Error connecting to server</div>`;
  }
}

function renderSampleList(filterQuery = "") {
  const query = filterQuery.toLowerCase().trim();
  
  // Filter samples
  const filtered = state.samples.filter(s => {
    if (!query) return true;
    return (
      s.filename.toLowerCase().includes(query) ||
      s.title.toLowerCase().includes(query) ||
      s.description.toLowerCase().includes(query)
    );
  });

  // Group by category
  const groups = {};
  filtered.forEach(s => {
    const cat = s.category;
    if (!groups[cat]) {
      groups[cat] = { order: s.category_order, items: [] };
    }
    groups[cat].items.push(s);
  });

  const sortedCategories = Object.keys(groups).sort((a, b) => groups[a].order - groups[b].order);

  if (sortedCategories.length === 0) {
    el.sampleList.innerHTML = `<div class="empty-row">No samples match "${filterQuery}"</div>`;
    return;
  }

  let html = "";
  sortedCategories.forEach(cat => {
    const { items } = groups[cat];
    html += `
      <div class="category-group">
        <div class="category-title" onclick="toggleCategory(this)">
          <span>${cat}</span>
          <span style="font-size: 10px; opacity: 0.7;">(${items.length})</span>
        </div>
        <div class="category-items">
          ${items.map(s => `
            <div class="sample-item ${state.activeSampleId === s.id ? 'active' : ''}" 
                 data-id="${s.id}" 
                 onclick="selectSample('${s.id}')">
              <div class="sample-item-info">
                <span class="sample-item-title">${escapeHtml(s.title || s.filename)}</span>
                <span class="sample-item-desc">${escapeHtml(s.filename)}</span>
              </div>
              <span class="badge-pill status-${s.expected.exit_code}">
                ${s.expected.exit_code === 0 ? 'OK' : s.expected.exit_code === 1 ? 'ERR' : 'RT'}
              </span>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  });

  el.sampleList.innerHTML = html;
}

window.toggleCategory = function(titleEl) {
  const itemsEl = titleEl.nextElementSibling;
  if (itemsEl) {
    itemsEl.classList.toggle("hidden");
  }
};

window.selectSample = function(id) {
  const sample = state.samples.find(s => s.id === id);
  if (!sample) return;

  state.activeSampleId = id;
  state.activeSample = sample;
  state.originalCode = sample.code;
  setEditorValue(sample.code);
  setIsDirty(false);

  el.activeFilename.textContent = sample.path;
  el.currentTitle.textContent = sample.title || sample.filename;
  el.currentDesc.textContent = sample.description ? `— ${sample.description}` : "";

  // Update active state in sidebar
  document.querySelectorAll(".sample-item").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-id") === id);
  });

  // Render expected spec in Comparison tab
  renderExpectedSpec(sample.expected);
};

function renderExpectedSpec(expected) {
  if (!expected) {
    el.expectedExitCode.textContent = "0 (Assumed)";
    el.expectedStdout.textContent = "(no specific expectations)";
    el.expectedStderr.textContent = "(none)";
    return;
  }

  el.expectedExitCode.textContent = `${expected.exit_code} (${expected.exit_code === 0 ? 'Success' : expected.exit_code === 1 ? 'Compile Error' : 'Runtime Error'})`;
  el.expectedStdout.textContent = expected.stdout && expected.stdout.length > 0 ? expected.stdout.join("\n") : "(none)";
  el.expectedStderr.textContent = expected.stderr && expected.stderr.length > 0 ? expected.stderr.join("\n") : "(none)";
}

// ============================================================================
// Code Editor Features
// ============================================================================
function setupEditor() {
  const textarea = el.codeEditor;

  textarea.addEventListener("input", () => {
    updateLineNumbers();
    updateCursorStatus();
    setIsDirty(textarea.value !== state.originalCode);
  });

  textarea.addEventListener("keydown", handleEditorKeydown);
  textarea.addEventListener("click", updateCursorStatus);
  textarea.addEventListener("keyup", updateCursorStatus);
  textarea.addEventListener("scroll", syncScroll);
}

function handleEditorKeydown(e) {
  const textarea = el.codeEditor;

  // Run on Ctrl+Enter or Cmd+Enter
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    runCode();
    return;
  }

  // Save on Ctrl+S or Cmd+S
  if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
    e.preventDefault();
    saveActiveFile();
    return;
  }

  // Tab key: Insert 4 spaces
  if (e.key === "Tab") {
    e.preventDefault();
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const val = textarea.value;

    textarea.value = val.substring(0, start) + "    " + val.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + 4;
    updateLineNumbers();
    setIsDirty(true);
    return;
  }

  // Auto-close brackets & quotes
  const pairs = { '(': ')', '{': '}', '[': ']', '"': '"', "'": "'" };
  if (pairs[e.key]) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    if (start === end) {
      const val = textarea.value;
      const nextChar = val[start];
      // Only auto-close if followed by whitespace or closing char
      if (!nextChar || /\s|\)|\}|\]|;/.test(nextChar)) {
        e.preventDefault();
        const closeChar = pairs[e.key];
        textarea.value = val.substring(0, start) + e.key + closeChar + val.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + 1;
        setIsDirty(true);
      }
    }
  }
}

function syncScroll() {
  el.lineNumbers.scrollTop = el.codeEditor.scrollTop;
}

function setEditorValue(val) {
  el.codeEditor.value = val;
  updateLineNumbers();
  updateCursorStatus();
}

function updateLineNumbers() {
  const lines = el.codeEditor.value.split("\n").length;
  let numHtml = "";
  for (let i = 1; i <= lines; i++) {
    numHtml += `<div>${i}</div>`;
  }
  el.lineNumbers.innerHTML = numHtml;
  el.statusLines.textContent = `${lines} ${lines === 1 ? 'line' : 'lines'}`;
}

function updateCursorStatus() {
  const textarea = el.codeEditor;
  const pos = textarea.selectionStart;
  const val = textarea.value;
  const textBefore = val.substring(0, pos);
  const lines = textBefore.split("\n");
  const lineNum = lines.length;
  const colNum = lines[lines.length - 1].length + 1;

  el.statusCursor.textContent = `Line ${lineNum}, Col ${colNum}`;
}

function setIsDirty(dirty) {
  state.isDirty = dirty;
  el.dirtyIndicator.classList.toggle("hidden", !dirty);
}

// ============================================================================
// Execution & Compiler Output
// ============================================================================
async function runCode() {
  const code = el.codeEditor.value;
  const engine = el.engineSelect.value;
  const optimize = el.optToggle.checked;
  const sampleId = state.activeSampleId;

  // Visual state: Running
  el.runBtn.disabled = true;
  el.runBtn.querySelector(".btn-icon").textContent = "⏳";
  el.terminalOutput.textContent = `$ unitlang run ${engine === 'interp' ? '--interp ' : ''}${!optimize ? '--no-opt ' : ''}...\nCompiling and executing...`;

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        engine,
        optimize,
        sample_id: sampleId
      })
    });

    const result = await res.json();
    state.lastRunResult = result;

    // 1. Render Terminal Tab
    renderTerminalOutput(result);

    // 2. Render Expected vs Actual Output Tab
    renderComparison(result);

    // 3. Render TAC Tab
    renderTAC(result);

    // 4. Render Bytecode Tab
    renderBytecode(result);

    // 5. Render Symbols Tab
    renderSymbols(result);

    // 6. Render Stats Tab
    renderStats(result);

  } catch (err) {
    console.error("Run error:", err);
    el.terminalOutput.textContent = `Error executing compiler: ${err.message}`;
  } finally {
    el.runBtn.disabled = false;
    el.runBtn.querySelector(".btn-icon").textContent = "▶";
  }
}

function renderTerminalOutput(result) {
  // Format ANSI colors to HTML spans
  const colored = ansiToHtml(result.terminal || "(no output)");
  el.terminalOutput.innerHTML = colored;
  el.termExecTime.textContent = `${result.execution_time_ms} ms`;
}

function renderComparison(result) {
  const comp = result.comparison;
  const expected = result.expected;

  // Actual
  el.actualExitCode.textContent = `${result.exit_code} (${result.exit_code === 0 ? 'Success' : result.exit_code === 1 ? 'Compile Error' : 'Runtime Error'})`;
  el.actualStdout.textContent = result.stdout && result.stdout.length > 0 ? result.stdout.join("\n") : "(empty)";
  el.actualStderr.textContent = result.stderr && result.stderr.length > 0 ? result.stderr.join("\n") : "(empty)";

  // Status Banner & Badges
  if (comp.status === "PASS") {
    el.comparisonBanner.className = "comparison-banner banner-pass";
    el.bannerStatusIcon.textContent = "✅";
    el.bannerTitle.textContent = "PASSED: All compiler checks & outputs match specification";
    el.bannerSubtitle.textContent = `Exit status ${result.exit_code} matched expected behavior with 0 discrepancies.`;
    
    el.testStatusPill.className = "status-pill status-pass";
    el.testStatusPill.textContent = "PASS";
    
    el.actualStatusBadge.className = "badge-pill status-0";
    el.actualStatusBadge.textContent = "PASSED";

    el.diffMismatchBox.classList.add("hidden");
  } else if (comp.status === "FAIL") {
    el.comparisonBanner.className = "comparison-banner banner-fail";
    el.bannerStatusIcon.textContent = "❌";
    el.bannerTitle.textContent = "MISMATCH: Output differed from test specification";
    el.bannerSubtitle.textContent = `${comp.problems.length} discrepancy found between actual run and expected test results.`;

    el.testStatusPill.className = "status-pill status-fail";
    el.testStatusPill.textContent = "FAIL";

    el.actualStatusBadge.className = "badge-pill status-1";
    el.actualStatusBadge.textContent = "MISMATCH";

    // Show problems
    el.diffMismatchBox.classList.remove("hidden");
    el.mismatchList.innerHTML = comp.problems.map(p => `<li>${escapeHtml(p)}</li>`).join("");
  } else {
    // Custom program
    el.comparisonBanner.className = "comparison-banner";
    el.bannerStatusIcon.textContent = "ℹ️";
    el.bannerTitle.textContent = "Custom Code Execution";
    el.bannerSubtitle.textContent = `Executed with exit code ${result.exit_code}. Add '// expect: <value>' to specify expectations.`;

    el.testStatusPill.className = "status-pill status-ready";
    el.testStatusPill.textContent = result.exit_code === 0 ? "OK" : "ERR";

    el.actualStatusBadge.className = "badge-pill status-" + result.exit_code;
    el.actualStatusBadge.textContent = result.exit_code === 0 ? "SUCCESS" : "ERROR";

    el.diffMismatchBox.classList.add("hidden");
  }
}

function renderTAC(result) {
  if (!result.tac_optimized && !result.tac_unoptimized) {
    el.irOutput.textContent = "// TAC not available (compilation failed before IR generation)";
    return;
  }

  if (state.tacViewMode === "opt") {
    el.irOutput.textContent = result.tac_optimized || result.tac_unoptimized || "(empty TAC)";
  } else if (state.tacViewMode === "unopt") {
    el.irOutput.textContent = result.tac_unoptimized || "(empty TAC)";
  } else {
    // Side by side
    const unopt = (result.tac_unoptimized || "").split("\n");
    const opt = (result.tac_optimized || "").split("\n");
    const maxLines = Math.max(unopt.length, opt.length);
    let diffText = "/* UNOPTIMIZED TAC */".padEnd(42) + "/* OPTIMIZED TAC */\n";
    diffText += "-".repeat(84) + "\n";
    for (let i = 0; i < maxLines; i++) {
      const left = (unopt[i] || "").padEnd(42);
      const right = opt[i] || "";
      diffText += left + right + "\n";
    }
    el.irOutput.textContent = diffText;
  }
}

function renderBytecode(result) {
  if (!result.bytecode) {
    el.bytecodeOutput.textContent = "// Bytecode not available (compilation failed before codegen)";
    return;
  }
  el.bytecodeOutput.textContent = result.bytecode;
}

function renderSymbols(result) {
  const syms = result.symbols;
  if (!syms) return;

  // Units
  if (syms.units && syms.units.length > 0) {
    el.unitsTableBody.innerHTML = syms.units.map(u => `
      <tr>
        <td style="font-weight: 600; color: #60a5fa;">${escapeHtml(u.name)}</td>
        <td>${escapeHtml(u.dimension)}</td>
        <td>${u.scale}</td>
        <td><span class="badge-pill ${u.origin === 'built-in' ? 'status-0' : 'status-2'}">${escapeHtml(u.origin)}</span></td>
      </tr>
    `).join("");
  } else {
    el.unitsTableBody.innerHTML = `<tr><td colspan="4" class="empty-row">No units defined</td></tr>`;
  }

  // Globals
  if (syms.globals && syms.globals.length > 0) {
    el.globalsTableBody.innerHTML = syms.globals.map(g => `
      <tr>
        <td style="font-weight: 600;">${escapeHtml(g.name)}</td>
        <td>${escapeHtml(g.dimension)}</td>
      </tr>
    `).join("");
  } else {
    el.globalsTableBody.innerHTML = `<tr><td colspan="2" class="empty-row">(none)</td></tr>`;
  }

  // Functions
  if (syms.functions && syms.functions.length > 0) {
    el.functionsTableBody.innerHTML = syms.functions.map(f => `
      <tr>
        <td style="font-weight: 600; color: #a78bfa;">${escapeHtml(f.name)}</td>
        <td>(${escapeHtml(f.args)})</td>
        <td style="color: #34d399;">→ ${escapeHtml(f.return)}</td>
      </tr>
    `).join("");
  } else {
    el.functionsTableBody.innerHTML = `<tr><td colspan="3" class="empty-row">No polymorphic function calls inferred</td></tr>`;
  }
}

function renderStats(result) {
  const stats = result.stats || {};
  el.statTacReduction.textContent = stats.tac_before !== undefined ? `${stats.tac_before} → ${stats.tac_after}` : "-";
  el.statFolded.textContent = stats.folded !== undefined ? stats.folded : "-";
  el.statUnitFolds.textContent = stats.unit_folds !== undefined ? stats.unit_folds : "-";
  el.statConstantsPropagated.textContent = stats.propagated !== undefined ? stats.propagated : "-";
  el.statDeadCode.textContent = stats.dead !== undefined ? stats.dead : "-";
  el.statBytecodeReduction.textContent = stats.bc_before !== undefined ? `${stats.bc_before} → ${stats.bc_after}` : "-";
  el.statPeephole.textContent = stats.peephole !== undefined ? stats.peephole : "-";
  el.statVmSteps.textContent = stats.vm_steps !== undefined ? stats.vm_steps : (result.exit_code === 0 ? "Completed" : "N/A");
}

// ============================================================================
// Test Suite Batch Runner
// ============================================================================
async function runTestSuite() {
  switchTab("tab-runner");
  el.startTestSuiteBtn.disabled = true;
  el.progressContainer.classList.remove("hidden");
  el.progressBarFill.style.width = "30%";
  el.progressText.textContent = "Executing 59 test programs...";
  el.progressPercent.textContent = "30%";

  try {
    const res = await fetch("/api/run_all", { method: "POST" });
    const data = await res.json();
    state.testSuiteResults = data;

    el.progressBarFill.style.width = "100%";
    el.progressPercent.textContent = "100%";
    el.progressText.textContent = `Completed! ${data.passed} of ${data.total} passed.`;

    el.runnerBigStatus.textContent = data.failed === 0 ? "🎉 All 59 Tests Passed!" : `⚠️ ${data.failed} Tests Failed`;
    el.runnerSummaryText.textContent = `${data.passed} passed, ${data.failed} failed out of ${data.total} total programs.`;

    el.filterAllCount.textContent = data.total;
    el.filterPassCount.textContent = data.passed;
    el.filterFailCount.textContent = data.failed;

    renderTestSuiteTable("all");
  } catch (err) {
    console.error("Test suite run failed:", err);
    el.progressText.textContent = "Failed to run test suite: " + err.message;
  } finally {
    el.startTestSuiteBtn.disabled = false;
  }
}

function renderTestSuiteTable(filter = "all") {
  if (!state.testSuiteResults) return;

  const results = state.testSuiteResults.results.filter(r => {
    if (filter === "pass") return r.status === "PASS";
    if (filter === "fail") return r.status === "FAIL";
    return true;
  });

  if (results.length === 0) {
    el.testResultsBody.innerHTML = `<tr><td colspan="5" class="empty-row">No tests match filter "${filter}".</td></tr>`;
    return;
  }

  el.testResultsBody.innerHTML = results.map(r => `
    <tr>
      <td>
        <span class="badge-pill ${r.status === 'PASS' ? 'status-0' : 'status-1'}">
          ${r.status}
        </span>
      </td>
      <td><span style="color: var(--text-muted);">${escapeHtml(r.category)}</span></td>
      <td>
        <div style="font-weight: 500;">${escapeHtml(r.title)}</div>
        <div style="font-size: 10px; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(r.path)}</div>
      </td>
      <td>
        <span style="font-family: var(--font-mono);">
          exit ${r.exit_code} (exp ${r.expected_exit_code})
        </span>
      </td>
      <td>
        <button class="btn-sm" onclick="selectSample('${r.id}'); switchTab('tab-terminal'); runCode();">
          Open & Run
        </button>
      </td>
    </tr>
  `).join("");
}

// ============================================================================
// File Actions
// ============================================================================
async function saveActiveFile() {
  if (!state.activeSample) return;
  const path = state.activeSample.path;
  const code = el.codeEditor.value;

  try {
    const res = await fetch("/api/save_sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, code })
    });
    const data = await res.json();
    if (data.ok) {
      state.originalCode = code;
      state.activeSample.code = code;
      setIsDirty(false);
      showTemporaryStatus("File saved successfully!");
    }
  } catch (err) {
    alert("Save failed: " + err.message);
  }
}

function createNewScratchpad() {
  const scratchId = "scratchpad_" + Date.now();
  const defaultCode = `// UnitLang Scratchpad
qty distance = 100 * m;
qty time     = 9.58 * s;
qty speed    = distance / time;

print(speed);
`;
  state.activeSampleId = scratchId;
  state.activeSample = {
    id: scratchId,
    filename: "scratchpad.ul",
    path: "scratchpad.ul",
    title: "New Scratchpad",
    description: "Interactive scratchpad for testing custom UnitLang code",
    code: defaultCode,
    expected: null,
  };
  state.originalCode = defaultCode;
  setEditorValue(defaultCode);
  setIsDirty(false);

  el.activeFilename.textContent = "scratchpad.ul (custom)";
  el.currentTitle.textContent = "New Scratchpad";
  el.currentDesc.textContent = "— Custom scratchpad";

  renderExpectedSpec(null);
  switchTab("tab-terminal");
  runCode();
}

function showTemporaryStatus(text) {
  const original = el.statusLines.textContent;
  el.statusLines.textContent = text;
  setTimeout(() => {
    el.statusLines.textContent = original;
  }, 2000);
}

// ============================================================================
// UI Event Handlers & Tabs
// ============================================================================
function setupEventListeners() {
  // Run
  el.runBtn.addEventListener("click", runCode);

  // Test Suite
  el.testAllBtn.addEventListener("click", runTestSuite);
  el.startTestSuiteBtn.addEventListener("click", runTestSuite);

  // Save
  el.saveBtn.addEventListener("click", saveActiveFile);

  // Revert
  el.formatBtn.addEventListener("click", () => {
    if (confirm("Revert code to the original sample?")) {
      setEditorValue(state.originalCode);
      setIsDirty(false);
    }
  });

  // Copy
  el.copyCodeBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(el.codeEditor.value).then(() => {
      showTemporaryStatus("Code copied to clipboard!");
    });
  });

  // Clear terminal
  el.clearTermBtn.addEventListener("click", () => {
    el.terminalOutput.textContent = "$ unitlang --ready\n";
  });

  // Search
  el.sampleSearch.addEventListener("input", (e) => {
    renderSampleList(e.target.value);
  });

  // New Scratchpad
  el.newScratchpadBtn.addEventListener("click", createNewScratchpad);

  // Tabs
  el.tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      switchTab(btn.getAttribute("data-tab"));
    });
  });

  // IR Views
  el.irViewOpt.addEventListener("click", () => setTacView("opt"));
  el.irViewUnopt.addEventListener("click", () => setTacView("unopt"));
  el.irViewDiff.addEventListener("click", () => setTacView("diff"));

  // Test filter chips
  el.filterChips.forEach(chip => {
    chip.addEventListener("click", () => {
      el.filterChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      renderTestSuiteTable(chip.getAttribute("data-filter"));
    });
  });
}

function switchTab(tabId) {
  el.tabBtns.forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === tabId));
  el.tabPanes.forEach(p => p.classList.toggle("active", p.id === tabId));
}

function setTacView(mode) {
  state.tacViewMode = mode;
  el.irViewOpt.classList.toggle("active", mode === "opt");
  el.irViewUnopt.classList.toggle("active", mode === "unopt");
  el.irViewDiff.classList.toggle("active", mode === "diff");
  if (state.lastRunResult) {
    renderTAC(state.lastRunResult);
  }
}

// Helper: ANSI color to HTML converter
function ansiToHtml(str) {
  return escapeHtml(str)
    .replace(/\033\[31m([\s\S]*?)\033\[0m/g, '<span style="color: #ef4444; font-weight: 500;">$1</span>')
    .replace(/\033\[32m([\s\S]*?)\033\[0m/g, '<span style="color: #10b981;">$1</span>')
    .replace(/\033\[33m([\s\S]*?)\033\[0m/g, '<span style="color: #f59e0b;">$1</span>')
    .replace(/\033\[34m([\s\S]*?)\033\[0m/g, '<span style="color: #3b82f6;">$1</span>')
    .replace(/\033\[36m([\s\S]*?)\033\[0m/g, '<span style="color: #06b6d4;">$1</span>')
    .replace(/\033\[0m/g, '');
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Start app
document.addEventListener("DOMContentLoaded", init);
