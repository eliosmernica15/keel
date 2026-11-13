/**
 * Neon Snake - Enhanced Edition
 * A polished Snake game with levels, pause, sound, mobile controls, and more.
 */

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");
const scoreElement = document.getElementById("score");
const highScoreElement = document.getElementById("highScore");
const levelElement = document.getElementById("level");
const finalScoreElement = document.getElementById("finalScore");
const highScoreMsgElement = document.getElementById("highScoreMsg");
const startScreen = document.getElementById("startScreen");
const pauseScreen = document.getElementById("pauseScreen");
const gameOverScreen = document.getElementById("gameOverScreen");
const startBtn = document.getElementById("startBtn");
const resumeBtn = document.getElementById("resumeBtn");
const playAgainBtn = document.getElementById("playAgainBtn");
const mainMenuBtn = document.getElementById("mainMenuBtn");
const difficultySelect = document.getElementById("difficulty");

// Game settings
const GRID_SIZE = 20;
const TILE_COUNT = canvas.width / GRID_SIZE;

// Difficulty speeds (ms per frame)
const DIFFICULTY_SPEEDS = {
    1: 150,   // Easy
    2: 100,   // Medium
    3: 70,    // Hard
    4: 45     // Insane
};

// Game state
let snake = [];
let food = { x: 0, y: 0 };
let dx = 0;
let dy = 0;
let nextDx = 0;
let nextDy = 0;
let score = 0;
let highScore = 0;
let level = 1;
let gameSpeed = 100;
let gameInterval = null;
let isGameOver = false;
let isPaused = true;
let isMuted = false;
let difficulty = 2;
let foodEatenThisLevel = 0;
const FOOD_PER_LEVEL = 5;

// Audio context for sound effects
let audioCtx = null;

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
}

function playSound(type) {
    if (isMuted || !audioCtx) return;
    
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    
    const now = audioCtx.currentTime;
    
    if (type === 'eat') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(600, now);
        osc.frequency.exponentialRampToValueAtTime(1200, now + 0.1);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.1);
        osc.start(now);
        osc.stop(now + 0.1);
    } else if (type === 'levelup') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(400, now);
        osc.frequency.linearRampToValueAtTime(800, now + 0.1);
        osc.frequency.linearRampToValueAtTime(1200, now + 0.2);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.3);
    } else if (type === 'gameover') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(200, now);
        osc.frequency.linearRampToValueAtTime(100, now + 0.5);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.linearRampToValueAtTime(0.01, now + 0.5);
        osc.start(now);
        osc.stop(now + 0.5);
    } else if (type === 'move') {
        // subtle tick
        osc.type = 'sine';
        osc.frequency.setValueAtTime(100, now);
        gain.gain.setValueAtTime(0.02, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
        osc.start(now);
        osc.stop(now + 0.05);
    }
}

function initGame() {
    // Start snake in the middle
    const startX = Math.floor(TILE_COUNT / 2);
    const startY = Math.floor(TILE_COUNT / 2);
    snake = [
        { x: startX, y: startY },
        { x: startX - 1, y: startY },
        { x: startX - 2, y: startY }
    ];
    dx = 1;
    dy = 0;
    nextDx = 1;
    nextDy = 0;
    score = 0;
    level = 1;
    foodEatenThisLevel = 0;
    gameSpeed = DIFFICULTY_SPEEDS[difficulty];
    
    scoreElement.textContent = score;
    levelElement.textContent = level;
    highScoreElement.textContent = highScore;
    
    placeFood();
    isGameOver = false;
    isPaused = false;
    
    startScreen.style.display = 'none';
    pauseScreen.style.display = 'none';
    gameOverScreen.style.display = 'none';
    
    if (gameInterval) clearInterval(gameInterval);
    gameInterval = setInterval(gameLoop, gameSpeed);
    
    initAudio();
}

function placeFood() {
    let valid = false;
    while (!valid) {
        food = {
            x: Math.floor(Math.random() * TILE_COUNT),
            y: Math.floor(Math.random() * TILE_COUNT)
        };
        valid = true;
        for (let segment of snake) {
            if (segment.x === food.x && segment.y === food.y) {
                valid = false;
                break;
            }
        }
    }
}

function gameLoop() {
    if (isGameOver || isPaused) return;
    
    dx = nextDx;
    dy = nextDy;
    
    const head = { x: snake[0].x + dx, y: snake[0].y + dy };
    
    // Wall collision
    if (head.x < 0 || head.x >= TILE_COUNT || head.y < 0 || head.y >= TILE_COUNT) {
        gameOver();
        return;
    }
    
    // Self collision
    for (let segment of snake) {
        if (head.x === segment.x && head.y === segment.y) {
            gameOver();
            return;
        }
    }
    
    snake.unshift(head);
    
    // Check food collision
    if (head.x === food.x && head.y === food.y) {
        score += 10;
        foodEatenThisLevel++;
        playSound('eat');
        
        // Level up
        if (foodEatenThisLevel >= FOOD_PER_LEVEL) {
            level++;
            foodEatenThisLevel = 0;
            gameSpeed = Math.max(40, gameSpeed - 15);
            clearInterval(gameInterval);
            gameInterval = setInterval(gameLoop, gameSpeed);
            playSound('levelup');
        }
        
        scoreElement.textContent = score;
        levelElement.textContent = level;
        placeFood();
    } else {
        snake.pop();
    }
    
    draw();
}

function draw() {
    // Clear canvas
    ctx.fillStyle = '#05050a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw grid (subtle)
    ctx.strokeStyle = '#1a1a2e';
    ctx.lineWidth = 1;
    for (let i = 0; i <= TILE_COUNT; i++) {
        ctx.beginPath();
        ctx.moveTo(i * GRID_SIZE, 0);
        ctx.lineTo(i * GRID_SIZE, canvas.height);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, i * GRID_SIZE);
        ctx.lineTo(canvas.width, i * GRID_SIZE);
        ctx.stroke();
    }
    
    // Draw food with glow
    ctx.fillStyle = '#ff4757';
    ctx.shadowBlur = 15;
    ctx.shadowColor = '#ff4757';
    ctx.fillRect(food.x * GRID_SIZE + 2, food.y * GRID_SIZE + 2, GRID_SIZE - 4, GRID_SIZE - 4);
    ctx.shadowBlur = 0;
    
    // Draw snake
    snake.forEach((segment, index) => {
        if (index === 0) {
            ctx.fillStyle = '#00ff88';
            ctx.shadowBlur = 10;
            ctx.shadowColor = '#00ff88';
        } else {
            // Gradient effect for body
            const intensity = Math.max(100, 255 - index * 10);
            ctx.fillStyle = `rgb(0, ${intensity}, 136)`;
            ctx.shadowBlur = 5;
            ctx.shadowColor = '#0088ff';
        }
        ctx.fillRect(segment.x * GRID_SIZE + 1, segment.y * GRID_SIZE + 1, GRID_SIZE - 2, GRID_SIZE - 2);
        ctx.shadowBlur = 0;
    });
}

function gameOver() {
    isGameOver = true;
    clearInterval(gameInterval);
    playSound('gameover');
    
    if (score > highScore) {
        highScore = score;
        localStorage.setItem('neonSnakeHighScore', highScore);
        highScoreElement.textContent = highScore;
        highScoreMsgElement.textContent = '🎉 NEW HIGH SCORE!';
        highScoreMsgElement.style.color = '#ff00ff';
    } else {
        highScoreMsgElement.textContent = `High Score: ${highScore}`;
        highScoreMsgElement.style.color = '#00ff88';
    }
    
    finalScoreElement.textContent = score;
    gameOverScreen.style.display = 'flex';
}

function showStartScreen() {
    isPaused = true;
    isGameOver = false;
    clearInterval(gameInterval);
    startScreen.style.display = 'flex';
    pauseScreen.style.display = 'none';
    gameOverScreen.style.display = 'none';
    
    // Load high score
    const savedHighScore = localStorage.getItem('neonSnakeHighScore');
    if (savedHighScore) {
        highScore = parseInt(savedHighScore);
        highScoreElement.textContent = highScore;
    }
}

function togglePause() {
    if (isGameOver) return;
    isPaused = !isPaused;
    pauseScreen.style.display = isPaused ? 'flex' : 'none';
}

function handleInput(key) {
    switch (key) {
        case 'ArrowUp':
        case 'w':
        case 'W':
            if (dy === 0) { nextDx = 0; nextDy = -1; }
            break;
        case 'ArrowDown':
        case 's':
        case 'S':
            if (dy === 0) { nextDx = 0; nextDy = 1; }
            break;
        case 'ArrowLeft':
        case 'a':
        case 'A':
            if (dx === 0) { nextDx = -1; nextDy = 0; }
            break;
        case 'ArrowRight':
        case 'd':
        case 'D':
            if (dx === 0) { nextDx = 1; nextDy = 0; }
            break;
        case 'p':
        case 'P':
            togglePause();
            break;
        case 'm':
        case 'M':
            isMuted = !isMuted;
            break;
    }
}

// Keyboard controls
document.addEventListener('keydown', (e) => {
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' ', 'p', 'P', 'm', 'M'].includes(e.key)) {
        e.preventDefault();
    }
    handleInput(e.key);
});

// WASD controls (prevent scrolling)
document.addEventListener('keydown', (e) => {
    if (['w', 'W', 'a', 'A', 's', 'S', 'd', 'D'].includes(e.key)) {
        e.preventDefault();
    }
});

// Touch / mobile controls
document.querySelectorAll('.dir-btn').forEach(btn => {
    btn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        handleInput(e.target.dataset.dir);
    });
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        handleInput(e.target.dataset.dir);
    });
});

// Button handlers
startBtn.addEventListener('click', () => {
    difficulty = parseInt(difficultySelect.value);
    initGame();
});

resumeBtn.addEventListener('click', () => {
    togglePause();
});

playAgainBtn.addEventListener('click', () => {
    difficulty = parseInt(difficultySelect.value);
    initGame();
});

mainMenuBtn.addEventListener('click', () => {
    showStartScreen();
});

// Initialize on load
showStartScreen();