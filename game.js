/**
 * K-Redactle — game.js
 * Pure static game logic. Imports pre-processed article data from data/articles.js
 */

import { ARTICLES } from './data/articles.js';

// ── State ─────────────────────────────────────────────────────────────────────
let state = {
  article: null,        // current article data
  guesses: [],          // { word, count, correct }
  revealedLemmas: new Set(),
  totalRedactable: 0,
  totalRevealed: 0,
  won: false,
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const loadingScreen  = $('loading-screen');
const app            = $('app');
const winOverlay     = $('win-overlay');
const giveupOverlay  = $('giveup-overlay');
const guessInput     = $('guess-input');
const guessBtn       = $('guess-btn');
const guessError     = $('guess-error');
const guessHistory   = $('guess-history');
const articleContent = $('article-content');
const totalGuessesEl = $('total-guesses');
const totalRevealedEl= $('total-revealed');
const totalTokensEl  = $('total-tokens');
const progressBar    = $('progress-bar');
const progressLabel  = $('progress-label');
const headerProgress = $('header-progress');
const howToPlay      = $('how-to-play');
const articleTitleEl = $('article-title-display');

// ── Entry ─────────────────────────────────────────────────────────────────────
function init() {
  setTimeout(() => startGame(), 300);

  guessBtn.addEventListener('click', submitGuess);
  guessInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') submitGuess();
  });
  $('give-up-btn').addEventListener('click', giveUp);
  $('how-to-play-btn').addEventListener('click', () => howToPlay.classList.toggle('hidden'));
  $('close-how-to-play').addEventListener('click', () => howToPlay.classList.add('hidden'));
  $('play-again-btn').addEventListener('click', () => { winOverlay.classList.add('hidden'); startGame(); });
  $('play-again-btn-2').addEventListener('click', () => { giveupOverlay.classList.add('hidden'); startGame(); });
  $('reveal-btn-win').addEventListener('click', () => winOverlay.classList.add('hidden'));
  $('close-win-overlay').addEventListener('click', () => winOverlay.classList.add('hidden'));
  $('reveal-btn-giveup').addEventListener('click', () => {
    giveupOverlay.classList.add('hidden');
    revealEverything();
  });

  window.addEventListener('hashchange', () => {
    // If the hash changed, we likely want to start a new game with that article
    startGame();
  });
}

function startGame() {
  // Pick an article: check for hash index first (e.g. index.html#2)
  let articleIndex = -1;
  const hash = window.location.hash.slice(1);
  if (hash && !isNaN(hash)) {
    articleIndex = parseInt(hash, 10);
  }

  const article = (articleIndex >= 0 && articleIndex < ARTICLES.length)
    ? ARTICLES[articleIndex]
    : ARTICLES[Math.floor(Math.random() * ARTICLES.length)];

  state = {
    article,
    guesses: [],
    revealedLemmas: new Set(),
    totalRedactable: 0,
    totalRevealed: 0,
    won: false,
  };

  renderArticle(article);
  updateStats();

  // Hide loading, show app
  loadingScreen.classList.add('fade-out');
  setTimeout(() => {
    loadingScreen.style.display = 'none';
    app.classList.remove('hidden');
  }, 500);

  // Reset sidebar
  guessHistory.innerHTML = '';
  guessInput.value = '';
  guessError.classList.add('hidden');
  winOverlay.classList.add('hidden');
  giveupOverlay.classList.add('hidden');

  setTimeout(() => guessInput.focus(), 600);
}

// ── Render ────────────────────────────────────────────────────────────────────

/** Render the full article into #article-content */
function renderArticle(article) {
  // Title bar
  renderTitleBar(article);

  // Count redactable tokens total
  let count = 0;
  article.paragraphs.forEach(para =>
    para.forEach(seg => { if (seg.redactable) count++; })
  );
  state.totalRedactable = count;
  totalTokensEl.textContent = count;

  // Build paragraphs
  articleContent.innerHTML = '';
  article.paragraphs.forEach((para, pi) => {
    const p = document.createElement('p');
    para.forEach((seg, si) => {
      const span = buildTokenSpan(seg, pi, si);
      p.appendChild(span);
    });
    articleContent.appendChild(p);
  });
}

function renderTitleBar(article) {
  // Render title: redact lemmas that need to be guessed
  articleTitleEl.innerHTML = '';
  const titleTokens = buildTitleTokens(article);
  titleTokens.forEach(el => articleTitleEl.appendChild(el));
}

function buildTitleTokens(article) {
  // Title is just the raw title string. Redact each title lemma's surface form.
  const titleLemmasSet = new Set(article.titleLemmas);
  const els = [];

  // Split title by the title lemmas occurring in it
  // Simple approach: render entire title as one or more tokens
  // We check each titleLemma against the title surface
  let title = article.title;

  // Check if all lemmas are revealed
  const allRevealed = article.titleLemmas.every(l => state.revealedLemmas.has(l));
  if (allRevealed) {
    const span = document.createElement('span');
    span.className = 'token-title-revealed';
    span.textContent = title;
    els.push(span);
  } else {
    // Show redacted blocks for each character
    const span = document.createElement('span');
    span.className = 'token-redacted';
    span.title = `${title.length}자`;
    
    for (let i = 0; i < title.length; i++) {
      const charBlock = document.createElement('span');
      charBlock.className = 'token-redacted-char';
      span.appendChild(charBlock);
    }
    els.push(span);
  }
  return els;
}

function buildTokenSpan(seg, pi, si) {
  if (!seg.redactable) {
    const span = document.createElement('span');
    span.className = 'token';
    span.textContent = seg.surface;
    return span;
  }

  const revealed = state.revealedLemmas.has(seg.lemma);
  const span = document.createElement('span');
  span.dataset.pi = pi;
  span.dataset.si = si;
  span.dataset.lemma = seg.lemma;

  if (revealed) {
    span.className = 'token token-revealed';
    span.textContent = seg.surface;
  } else {
    span.className = 'token token-redacted';
    span.title = `${seg.surface.length}자`;
    
    // Character count badge
    const badge = document.createElement('span');
    badge.className = 'char-count-badge';
    badge.textContent = `${seg.surface.length}자`;
    span.appendChild(badge);

    for (let i = 0; i < seg.surface.length; i++) {
      const charBlock = document.createElement('span');
      charBlock.className = 'token-redacted-char';
      span.appendChild(charBlock);
    }

    // Toggle character count on click
    span.addEventListener('click', (e) => {
      e.stopPropagation();
      // Remove from others
      document.querySelectorAll('.token-redacted.show-count').forEach(el => {
        if (el !== span) el.classList.remove('show-count');
      });
      span.classList.toggle('show-count');
    });
  }
  return span;
}

// ── Guess ─────────────────────────────────────────────────────────────────────

function normalizeGuess(raw) {
  return raw.trim().replace(/\s+/g, '');
}

function submitGuess() {
  if (state.won) return;
  const raw = guessInput.value;
  const word = normalizeGuess(raw);
  if (!word) return;

  if (word.length < 1) {
    showError('단어를 입력해주세요.');
    return;
  }

  // Check duplicate
  if (state.guesses.some(g => g.word === word)) {
    showError('이미 추측한 단어입니다.');
    return;
  }
  hideError();

  // Count matches across all paragraphs
  let matchCount = 0;
  state.article.paragraphs.forEach(para => {
    para.forEach(seg => {
      if (seg.redactable && seg.lemma === word) matchCount++;
    });
  });

  const correct = matchCount > 0;
  if (correct) {
    state.revealedLemmas.add(word);
    state.totalRevealed += matchCount;
  }

  state.guesses.unshift({ word, count: matchCount, correct });
  addHistoryItem(word, matchCount, correct);

  if (correct) revealTokensByLemma(word);
  updateStats();

  // Check win: all title lemmas guessed
  const won = state.article.titleLemmas.every(l => state.revealedLemmas.has(l));
  if (won) {
    state.won = true;
    setTimeout(() => showWin(), 600);
  }

  guessInput.value = '';
  guessInput.focus();
}

function revealTokensByLemma(lemma) {
  // Update all matching spans in article
  document.querySelectorAll(`[data-lemma="${lemma}"]`).forEach(span => {
    const pi = +span.dataset.pi;
    const si = +span.dataset.si;
    const seg = state.article.paragraphs[pi][si];
    span.className = 'token token-revealed';
    span.textContent = seg.surface;
    span.removeAttribute('style');
    span.removeAttribute('title');
  });

  // Re-render title bar in case title lemma was guessed
  renderTitleBar(state.article);
}

function addHistoryItem(word, count, correct) {
  const li = document.createElement('li');
  li.className = `guess-item ${correct ? 'correct' : 'wrong'}`;
  li.innerHTML = `
    <span class="guess-item-word">${escHtml(word)}</span>
    <span class="guess-item-count">${correct ? `+${count}` : '✗'}</span>
  `;
  guessHistory.insertBefore(li, guessHistory.firstChild);
}

function updateStats() {
  const guessCount = state.guesses.length;
  totalGuessesEl.textContent = guessCount;
  totalRevealedEl.textContent = state.totalRevealed;

  const pct = state.totalRedactable > 0
    ? Math.round((state.totalRevealed / state.totalRedactable) * 100)
    : 0;
  progressBar.style.width = `${pct}%`;
  progressLabel.textContent = `${pct}% 공개됨`;
  headerProgress.textContent = `${guessCount}회 추측 · ${pct}% 공개`;
}

function showWin() {
  const title = state.article.title;
  const url = state.article.sourceUrl || `https://ko.wikipedia.org/wiki/${title.replace(/ /g, '_')}`;
  
  $('win-article-title').textContent = title;
  $('win-guess-count').textContent = state.guesses.length;
  $('win-correct-count').textContent = state.guesses.filter(g => g.correct).length;
  
  // Update link
  const link = $('win-wiki-link');
  if (link) {
    link.href = url;
    link.textContent = title;
  }
  
  winOverlay.classList.remove('hidden');
}

function giveUp() {
  if (state.won) return;
  // Reveal everything
  state.article.paragraphs.forEach(para => {
    para.forEach(seg => {
      if (seg.redactable) state.revealedLemmas.add(seg.lemma);
    });
  });
  state.totalRevealed = state.totalRedactable;

  // Re-render all tokens
  document.querySelectorAll('.token-redacted[data-lemma]').forEach(span => {
    const pi = +span.dataset.pi;
    const si = +span.dataset.si;
    const seg = state.article.paragraphs[pi][si];
    if (seg) {
      span.className = 'token token-revealed';
      span.style.color = 'var(--text-muted)';
      span.textContent = seg.surface;
      span.removeAttribute('style');
    }
  });

  // Reveal title
  articleTitleEl.innerHTML = '';
  const span = document.createElement('span');
  span.className = 'token token-title-revealed';
  span.textContent = state.article.title;
  articleTitleEl.appendChild(span);

  updateStats();

  $('giveup-article-title').textContent = state.article.title;
  $('giveup-guess-count').textContent = state.guesses.length;
  $('giveup-correct-count').textContent = state.guesses.filter(g => g.correct).length;
  
  // Update link
  const title = state.article.title;
  const url = state.article.sourceUrl || `https://ko.wikipedia.org/wiki/${title.replace(/ /g, '_')}`;
  const link = $('giveup-wiki-link');
  if (link) {
    link.href = url;
    link.textContent = title;
  }
  
  giveupOverlay.classList.remove('hidden');
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function showError(msg) {
  guessError.textContent = msg;
  guessError.classList.remove('hidden');
}
function hideError() {
  guessError.classList.add('hidden');
}
function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function revealEverything() {
  state.article.paragraphs.forEach((p, pIdx) => {
    p.forEach((seg, sIdx) => {
      if (seg.redactable && seg.lemmas) {
        seg.lemmas.forEach(l => state.revealedLemmas.add(l.toLowerCase()));
      }
    });
  });
  renderArticle(state.article);
  renderTitleBar(state.article);
}

// Global click listener to hide character count badges
document.addEventListener('click', () => {
  document.querySelectorAll('.token-redacted.show-count').forEach(el => {
    el.classList.remove('show-count');
  });
});

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
