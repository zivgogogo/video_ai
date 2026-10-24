/**
 * 交互式粒子网络系统 — 鼠标跟随 + 粒子连线
 * 营造高端科技感背景效果
 */
(function () {
  const canvas = document.getElementById('particle-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');

  // ── 配置 ──────────────────────────────────────────────
  const CONFIG = {
    particleCount: 80,
    connectionDistance: 150,
    mouseRadius: 200,
    particleSpeed: 0.4,
    particleSize: 2,
    colors: {
      particle: 'rgba(99, 102, 241, 0.6)',
      connection: 'rgba(99, 102, 241, 0.15)',
      mouseConnection: 'rgba(139, 92, 246, 0.35)',
      mouseParticle: 'rgba(139, 92, 246, 0.9)',
    },
  };

  // ── 状态 ──────────────────────────────────────────────
  let particles = [];
  let mouse = { x: -1000, y: -1000, isMoving: false };
  let mouseTimer = null;
  let width, height;
  let animationId;

  // ── 粒子类 ────────────────────────────────────────────
  class Particle {
    constructor() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * CONFIG.particleSpeed;
      this.vy = (Math.random() - 0.5) * CONFIG.particleSpeed;
      this.size = Math.random() * CONFIG.particleSize + 0.5;
      this.alpha = Math.random() * 0.5 + 0.3;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;

      // 边界反弹
      if (this.x < 0 || this.x > width) this.vx *= -1;
      if (this.y < 0 || this.y > height) this.vy *= -1;

      // 微弱的向心力
      this.vx += (Math.random() - 0.5) * 0.03;
      this.vy += (Math.random() - 0.5) * 0.03;

      // 速度限制
      const speed = Math.sqrt(this.vx * this.vx + this.vy * this.vy);
      if (speed > CONFIG.particleSpeed * 2) {
        this.vx = (this.vx / speed) * CONFIG.particleSpeed * 2;
        this.vy = (this.vy / speed) * CONFIG.particleSpeed * 2;
      }
    }

    draw(ctx) {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = CONFIG.colors.particle;
      ctx.globalAlpha = this.alpha;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }

  // ── 初始化 ────────────────────────────────────────────
  function init() {
    resize();
    particles = [];
    for (let i = 0; i < CONFIG.particleCount; i++) {
      particles.push(new Particle());
    }
  }

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
  }

  // ── 鼠标交互 ──────────────────────────────────────────
  function onMouseMove(e) {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    mouse.isMoving = true;
    clearTimeout(mouseTimer);
    mouseTimer = setTimeout(() => {
      mouse.isMoving = false;
    }, 3000);
  }

  function onMouseLeave() {
    mouse.isMoving = false;
    mouse.x = -1000;
    mouse.y = -1000;
  }

  // ── 渲染循环 ──────────────────────────────────────────
  function draw() {
    ctx.clearRect(0, 0, width, height);

    // 更新和绘制粒子
    for (const p of particles) {
      p.update();
      p.draw(ctx);
    }

    // 绘制粒子间连线
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < CONFIG.connectionDistance) {
          const alpha = (1 - dist / CONFIG.connectionDistance) * 0.25;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = CONFIG.colors.connection;
          ctx.globalAlpha = alpha;
          ctx.lineWidth = 0.5;
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }
    }

    // 鼠标与粒子连线（鼠标移动时）
    if (mouse.isMoving) {
      for (const p of particles) {
        const dx = p.x - mouse.x;
        const dy = p.y - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < CONFIG.mouseRadius) {
          // 连线
          const alpha = (1 - dist / CONFIG.mouseRadius) * 0.5;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.strokeStyle = CONFIG.colors.mouseConnection;
          ctx.globalAlpha = alpha;
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.globalAlpha = 1;

          // 粒子向鼠标微弱靠近
          const force = (1 - dist / CONFIG.mouseRadius) * 0.02;
          p.vx += (dx / dist) * force;
          p.vy += (dy / dist) * force;
        }
      }

      // 鼠标位置的光晕
      const gradient = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 60);
      gradient.addColorStop(0, 'rgba(139, 92, 246, 0.15)');
      gradient.addColorStop(1, 'rgba(139, 92, 246, 0)');
      ctx.beginPath();
      ctx.arc(mouse.x, mouse.y, 60, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    animationId = requestAnimationFrame(draw);
  }

  // ── 事件监听 ──────────────────────────────────────────
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', onMouseMove, { passive: true });
  window.addEventListener('mouseleave', onMouseLeave);
  document.addEventListener('touchmove', (e) => {
    mouse.x = e.touches[0].clientX;
    mouse.y = e.touches[0].clientY;
    mouse.isMoving = true;
  }, { passive: true });
  document.addEventListener('touchend', () => {
    mouse.isMoving = false;
  });

  // ── 启动 ──────────────────────────────────────────────
  init();
  draw();
})();
