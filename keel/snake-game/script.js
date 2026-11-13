const canvas = document.getElementById("snakeGame");
const ctx = canvas.getContext("2d");
const scoreElement = document.getElementById("score");

// Game settings
const box = 20; // Size of one square
const canvasSize = 400;

// Initialize snake
let snake = [];
snake[0] = { x: 10 * box, y: 10 * box };

// Initialize food
let food = {
    x: Math.floor(Math.random() * (canvasSize / box)) * box,
    y: Math.floor(Math.random() * (canvasSize / box)) * box
};

// Initialize score
let score = 0;

// Initialize direction
let d;

// Control the snake
document.addEventListener("keydown", direction);

function direction(event) {
    let key = event.keyCode;
    // Prevent snake from reversing
    if (key == 37 && d != "RIGHT") {
        d = "LEFT";
    } else if (key == 38 && d != "DOWN") {
        d = "UP";
    } else if (key == 39 && d != "LEFT") {
        d = "RIGHT";
    } else if (key == 40 && d != "UP") {
        d = "DOWN";
    }
}

// Collision detection function
function collision(head, array) {
    for (let i = 0; i < array.length; i++) {
        if (head.x == array[i].x && head.y == array[i].y) {
            return true;
        }
    }
    return false;
}

// Draw function
function draw() {
    // Clear canvas
    ctx.fillStyle = "black";
    ctx.fillRect(0, 0, canvasSize, canvasSize);

    // Draw snake
    for (let i = 0; i < snake.length; i++) {
        ctx.fillStyle = (i == 0) ? "#2ecc71" : "#27ae60";
        ctx.fillRect(snake[i].x, snake[i].y, box, box);
        
        // Add snake border
        ctx.strokeStyle = "#000";
        ctx.strokeRect(snake[i].x, snake[i].y, box, box);
    }

    // Draw food
    ctx.fillStyle = "#e74c3c";
    ctx.fillRect(food.x, food.y, box, box);

    // Old head position
    let snakeX = snake[0].x;
    let snakeY = snake[0].y;

    // Move direction
    if (d == "LEFT") snakeX -= box;
    if (d == "UP") snakeY -= box;
    if (d == "RIGHT") snakeX += box;
    if (d == "DOWN") snakeY += box;

    // Check if snake eats food
    if (snakeX == food.x && snakeY == food.y) {
        score++;
        scoreElement.innerHTML = score;
        food = {
            x: Math.floor(Math.random() * (canvasSize / box)) * box,
            y: Math.floor(Math.random() * (canvasSize / box)) * box
        };
        // Don't remove tail (snake grows)
    } else {
        // Remove tail
        snake.pop();
    }

    // New head
    let newHead = {
        x: snakeX,
        y: snakeY
    };

    // Game over rules
    if (snakeX < 0 || snakeX >= canvasSize || snakeY < 0 || snakeY >= canvasSize || collision(newHead, snake)) {
        clearInterval(game);
        alert("Game Over! Your score: " + score);
        resetGame();
    }

    snake.unshift(newHead);
}

// Game loop
let game = setInterval(draw, 100);

// Reset game function
function resetGame() {
    snake = [];
    snake[0] = { x: 10 * box, y: 10 * box };
    score = 0;
    scoreElement.innerHTML = score;
    d = null;
    food = {
        x: Math.floor(Math.random() * (canvasSize / box)) * box,
        y: Math.floor(Math.random() * (canvasSize / box)) * box
    };
    clearInterval(game);
    game = setInterval(draw, 100);
}