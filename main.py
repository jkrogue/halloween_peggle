# /// script
#     dependencies = [
#     "numpy",
#     #pygame",
#     "pygame.sndarray",
# ]
# ///
import numpy as np
import pygame
from pygame import sndarray
import asyncio
import math
import random
import sys
from dataclasses import dataclass
from typing import List, Tuple

_music_sound = None  # module-level cache so we don't regenerate each time

# --- Config ---
WIDTH, HEIGHT = 800, 960
FPS = 120
GRAVITY = 0.18
BOUNCE_DAMPING = 0.985
BALL_RADIUS = 8
PEG_RADIUS = 14
BUCKET_WIDTH, BUCKET_HEIGHT = 120, 18
AIM_POWER = 8.0  # slower launch speed
MAX_BALLS = 10
ORANGE_RATIO = 0.35
LEVEL_ROWS = 7
LEVEL_COLS = 11
ROW_SPACING = 82
COL_SPACING = 64
TOP_OFFSET = 200
SIDE_MARGIN = 62
SPEED_BOOST = 1.25  # speed multiplier on side bounce

pygame.mixer.pre_init(44100, -16, 2, 512)  # 44.1kHz, 16-bit signed, stereo, small buffer
pygame.init()
pygame.mixer.init()  # keep this if you already call it

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Halloween Peggle-ish 🎃")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arialrounded", 22)
headline_font = pygame.font.SysFont("arialrounded", 56, bold=True)

# Colors
BLACK = (10, 8, 16)
WHITE = (240, 240, 240)
MOON = (245, 245, 210)
PURPLE = (74, 32, 95)
DARK_PURPLE = (37, 17, 59)
ORANGE = (255, 140, 0)
BLUE = (80, 150, 255)
GREEN = (90, 200, 140)
RED = (255, 90, 90)
SMOKE = (200, 200, 220)
YELLOW = (255, 255, 120)
GOLD = (255, 215, 0)

# --- Utility ---
def clamp(x, a, b):
    return max(a, min(b, x))

# --- Entities ---
@dataclass
class Peg:
    x: float
    y: float
    r: float
    color: Tuple[int, int, int]
    active: bool = True
    hit_flash: float = 0.0
    orange: bool = False

    def draw(self, surf: pygame.Surface):
        if not self.active:
            return
        base = self.color
        if self.hit_flash > 0:
            glow = 80
            c = (clamp(base[0]+glow,0,255), clamp(base[1]+glow,0,255), clamp(base[2]+glow,0,255))
        else:
            c = base
        pygame.draw.circle(surf, (0,0,0), (int(self.x), int(self.y)+2), self.r+2)
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), self.r)
        if self.orange:
            eye_dx = 4
            eye_y = -3
            pygame.draw.circle(surf, BLACK, (int(self.x-eye_dx), int(self.y+eye_y)), 2)
            pygame.draw.circle(surf, BLACK, (int(self.x+eye_dx), int(self.y+eye_y)), 2)
            pygame.draw.polygon(surf, BLACK, [
                (self.x-5, self.y+4), (self.x+5, self.y+4), (self.x, self.y+9)
            ])

    def update(self, dt):
        if self.hit_flash > 0:
            self.hit_flash = max(0.0, self.hit_flash - dt*2)

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: Tuple[int,int,int]

    def update(self, dt):
        self.vy += GRAVITY*0.25
        self.x += self.vx
        self.y += self.vy
        self.life -= dt

    def draw(self, surf):
        if self.life <= 0:
            return
        alpha = clamp(int(255*min(1,self.life)), 0, 255)
        s = pygame.Surface((6,6), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (3,3), 3)
        surf.blit(s, (self.x-3, self.y-3))

@dataclass
class Ball:
    x: float
    y: float
    vx: float
    vy: float
    active: bool = True
    trail: List[Tuple[float,float]] = None

    def __post_init__(self):
        if self.trail is None:
            self.trail = []

    def update(self):
        """Update ball physics; return a list of event strings for SFX hooks."""
        events = []
        if not self.active:
            return events
        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy

        # Left wall bounce with boost
        if self.x < BALL_RADIUS:
            self.x = BALL_RADIUS
            self.vx *= -BOUNCE_DAMPING * SPEED_BOOST
            self.vy *= SPEED_BOOST
            events.append("bounce_wall")
        # Right wall bounce with boost
        if self.x > WIDTH - BALL_RADIUS:
            self.x = WIDTH - BALL_RADIUS
            self.vx *= -BOUNCE_DAMPING * SPEED_BOOST
            self.vy *= SPEED_BOOST
            events.append("bounce_wall")

        # Top bounce
        if self.y < BALL_RADIUS:
            self.y = BALL_RADIUS
            self.vy *= -BOUNCE_DAMPING
            events.append("bounce_top")

        # Trail
        self.trail.append((self.x, self.y))
        if len(self.trail) > 12:
            self.trail.pop(0)

        return events

    def draw(self, surf: pygame.Surface):
        for i, (tx, ty) in enumerate(self.trail):
            pygame.draw.circle(surf, (255,255,255), (int(tx),int(ty)), 3, 1)
        pygame.draw.circle(surf, WHITE, (int(self.x), int(self.y)), BALL_RADIUS)
        pygame.draw.circle(surf, BLACK, (int(self.x), int(self.y)), BALL_RADIUS, 1)

class Bucket:
    def __init__(self):
        self.w = BUCKET_WIDTH
        self.h = BUCKET_HEIGHT
        self.x = WIDTH/2 - self.w/2
        self.y = HEIGHT-64
        self.vx = 2.4

    def update(self):
        self.x += self.vx
        if self.x < 0 or self.x + self.w > WIDTH:
            self.vx *= -1
            self.x = clamp(self.x, 0, WIDTH-self.w)

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    def draw(self, surf):
        rect = self.rect()
        pygame.draw.rect(surf, (20,20,20), rect.inflate(4,4), border_radius=8)
        pygame.draw.rect(surf, GREEN, rect, border_radius=8)
        text = font.render("+1 Ball", True, WHITE)
        surf.blit(text, (rect.centerx - text.get_width()//2, rect.centery - text.get_height()//2))

# --- Level generation ---
def generate_level(seed=None) -> List[Peg]:
    if seed is not None:
        random.seed(seed)
    pegs: List[Peg] = []
    for r in range(LEVEL_ROWS):
        for c in range(LEVEL_COLS):
            x = SIDE_MARGIN + c*COL_SPACING + (r%2)*COL_SPACING/2
            y = TOP_OFFSET + r*ROW_SPACING
            jitter = random.uniform(-6,6)
            px = x + jitter
            py = y + random.uniform(-4,4)
            color = BLUE
            pegs.append(Peg(px, py, PEG_RADIUS, color))
    # mark some as orange
    orange_idx = random.sample(range(len(pegs)), int(len(pegs)*ORANGE_RATIO))
    for i in orange_idx:
        pegs[i].color = ORANGE
        pegs[i].orange = True
    # add a few spooky bonus greens (worth more points)
    for _ in range(6):
        p = random.choice(pegs)
        p.color = GREEN
        p.orange = False
    return pegs

# --- Collision ---
def ball_peg_collision(ball: Ball, peg: Peg):
    dx = ball.x - peg.x
    dy = ball.y - peg.y
    dist2 = dx*dx + dy*dy
    r = BALL_RADIUS + peg.r
    if dist2 <= r*r and peg.active:
        dist = math.sqrt(max(1e-6, dist2))
        nx, ny = dx/dist, dy/dist
        # push out
        overlap = r - dist
        ball.x += nx * overlap
        ball.y += ny * overlap
        # reflect
        vdotn = ball.vx*nx + ball.vy*ny
        ball.vx -= 2*vdotn*nx
        ball.vy -= 2*vdotn*ny
        ball.vx *= BOUNCE_DAMPING
        ball.vy *= BOUNCE_DAMPING
        return True
    return False

# --- Rendering helpers ---
def draw_background(surf):
    # Vertical gradient night sky
    for i in range(HEIGHT):
        t = i/HEIGHT
        r = int(DARK_PURPLE[0]*(1-t) + PURPLE[0]*t)
        g = int(DARK_PURPLE[1]*(1-t) + PURPLE[1]*t)
        b = int(DARK_PURPLE[2]*(1-t) + PURPLE[2]*t)
        pygame.draw.line(surf, (r,g,b), (0,i), (WIDTH,i))
    # Moon
    pygame.draw.circle(surf, MOON, (WIDTH-120, 120), 52)
    pygame.draw.circle(surf, (230,230,210), (WIDTH-100, 110), 8)
    pygame.draw.circle(surf, (232,232,212), (WIDTH-135, 140), 6)
    # Hills silhouettes
    pygame.draw.ellipse(surf, (20, 12, 24), (-200, HEIGHT-220, 600, 300))
    pygame.draw.ellipse(surf, (25, 15, 30), (200, HEIGHT-200, 700, 280))
    # Haunted house
    base = pygame.Rect(80, HEIGHT-210, 120, 160)
    pygame.draw.rect(surf, (25,25,40), base)
    pygame.draw.polygon(surf, (18,18,30), [(base.left-10, base.top), (base.right+10, base.top), (base.centerx, base.top-40)])
    # Windows
    for wx in (base.left+20, base.right-40):
        for wy in (base.top+30, base.top+90):
            pygame.draw.rect(surf, (250, 220, 120), (wx, wy, 20, 28))

def draw_bouncers(surf):
    # Glowing side bouncers for visibility
    left_rect = pygame.Rect(0, 0, 16, HEIGHT)
    right_rect = pygame.Rect(WIDTH-16, 0, 16, HEIGHT)
    glow_left = pygame.Surface((16, HEIGHT), pygame.SRCALPHA)
    glow_right = pygame.Surface((16, HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(glow_left, (*GOLD, 160), glow_left.get_rect())
    pygame.draw.rect(glow_right, (*GOLD, 160), glow_right.get_rect())
    surf.blit(glow_left, (0, 0))
    surf.blit(glow_right, (WIDTH-16, 0))

def draw_hud(surf, balls_left, score, orange_left, aiming, angle_line):
    bar = pygame.Rect(0,0, WIDTH, 70)
    pygame.draw.rect(surf, (14, 10, 22), bar)
    text = font.render(f"🎃 Balls: {balls_left}    🟠 Orange left: {orange_left}    ⭐ Score: {score}", True, WHITE)
    surf.blit(text, (16, 22))
    if aiming and angle_line:
        pygame.draw.line(surf, SMOKE, angle_line[0], angle_line[1], 2)

def draw_cannon(surf, pos, angle):
    base = (WIDTH//2, 90)
    pygame.draw.circle(surf, (30,30,40), (base[0], base[1]), 26)
    pygame.draw.circle(surf, (20,20,30), (base[0], base[1]), 26, 3)
    length = 54
    endx = base[0] + int(math.cos(angle)*length)
    endy = base[1] + int(math.sin(angle)*length)
    pygame.draw.line(surf, (80, 220, 160), base, (endx, endy), 8)

# --- Music ---
def play_halloween_music():
    """Generate and loop a spooky placeholder tone that works with a stereo mixer."""
    global _music_sound
    if _music_sound is not None:
        return  # already created/playing

    init = pygame.mixer.get_init()
    if not init:
        pygame.mixer.init()
        init = pygame.mixer.get_init()

    sample_rate, fmt, channels = init  # e.g., (44100, -16, 2)

    duration_sec = 3.0               # length of the loop
    n = int(sample_rate * duration_sec)

    # Two close frequencies to make it eerie
    f1 = 220.0   # A3
    f2 = 233.1   # ~Bb3 (minor second-ish)
    volume = 0.25

    # Build a stereo (n, channels) int16 array
    t = np.arange(n) / sample_rate
    wave = (np.sin(2*math.pi*f1*t) + 0.6*np.sin(2*math.pi*f2*t)) * 0.5
    wave = (volume * 32767 * wave).astype(np.int16)

    if channels == 1:
        audio = wave.reshape(-1, 1)
    else:
        # same signal in L/R; you can offset phase for extra creepiness
        audio = np.column_stack([wave, wave])

    # _music_sound = sndarray.make_sound(audio)
    # _music_sound.play(loops=-1)

# --- Sound FX (synth, no files needed) ---
class SoundFX:
    def __init__(self):
        self.cache: dict[tuple, pygame.mixer.Sound] = {}
        self.enabled = True

    def _tone(self, freq=440.0, ms=70, volume=0.35, shape="sine"):
        """Make or fetch a short beep/thunk tone (int16)."""
        if not self.enabled:
            return None

        init = pygame.mixer.get_init()
        if not init:
            try:
                pygame.mixer.init()
                init = pygame.mixer.get_init()
            except Exception:
                return None

        sample_rate, fmt, channels = init
        key = (round(freq, 2), ms, round(volume, 2), shape, sample_rate, channels)
        if key in self.cache:
            return self.cache[key]

        n = int(sample_rate * (ms / 1000.0))
        t = np.arange(n) / sample_rate

        # Basic waves
        if shape == "sine":
            w = np.sin(2 * math.pi * freq * t)
        elif shape == "triangle":
            # triangle via arcsin(sin()) method
            w = (2 / math.pi) * np.arcsin(np.sin(2 * math.pi * freq * t))
        elif shape == "square":
            w = np.sign(np.sin(2 * math.pi * freq * t))
        else:  # fallback
            w = np.sin(2 * math.pi * freq * t)

        # Simple click-softener: fast fade-in/out
        fade = min(0.008, ms / 1000.0 / 6)  # seconds
        fade_n = max(1, int(sample_rate * fade))
        env = np.ones(n, dtype=np.float32)
        env[:fade_n] = np.linspace(0, 1, fade_n)
        env[-fade_n:] = np.linspace(1, 0, fade_n)
        w = (w * env).astype(np.float32)

        # scale to int16
        wave = (volume * 32767 * w).astype(np.int16)

        if channels == 1:
            audio = wave.reshape(-1, 1)
        else:
            # tiny stereo variation for body
            audio = np.column_stack([wave, wave])

        # snd = sndarray.make_sound(audio)
        # self.cache[key] = snd
        # return snd

    # Public helpers
    def peg(self, color=(255, 255, 255)):
        """Higher pitch for orange, mid for blue, low for green."""
        if not self.enabled:
            return
        # Map color → freq
        if color == (255, 140, 0):      # ORANGE
            f = 900
        elif color == (90, 200, 140):   # GREEN
            f = 420
        else:                           # BLUE or default
            f = 640
        snd = self._tone(freq=f, ms=55, volume=0.28, shape="triangle")
        if snd: snd.play()

    def wall(self):
        """Thunk for wall/top bounces."""
        if not self.enabled:
            return
        snd = self._tone(freq=180, ms=60, volume=0.38, shape="square")
        if snd: snd.play()

    def launch(self):
        """Tiny ascending chirp."""
        if not self.enabled:
            return
        a = self._tone(freq=420, ms=40, volume=0.25, shape="sine")
        b = self._tone(freq=560, ms=40, volume=0.25, shape="sine")
        if a: a.play()
        if b:
            # slight delay by scheduling after first ends (approx)
            pygame.time.set_timer(pygame.USEREVENT + 5, 40, True)
            # Use a one-shot timer handler in the loop (added below)

    def bucket(self):
        """Rewardy 'ding'."""
        if not self.enabled:
            return
        a = self._tone(freq=660, ms=80, volume=0.32, shape="sine")
        b = self._tone(freq=990, ms=90, volume=0.28, shape="sine")
        if a: a.play()
        if b:
            pygame.time.set_timer(pygame.USEREVENT + 6, 70, True)

# Create a singleton
sfx = SoundFX()

# --- Game ---
class Game:
    def __init__(self):
        self.reset()
        self.level = 1
        self.music_started = False

    def reset(self):
        self.pegs = generate_level()
        self.ball: Ball | None = None
        self.balls_left = MAX_BALLS
        self.score = 0
        self.bucket = Bucket()
        self.particles: List[Particle] = []
        self.aim_angle = -math.pi/2
        self.state = "playing"  # "win", "lose"
        self.last_hit_colors = []  # for end-of-turn bonus

    def launch_ball(self, angle):
        if self.ball is not None and self.ball.active:
            return
        if self.balls_left <= 0:
            return
        base = (WIDTH//2, 90)
        vx = math.cos(angle) * AIM_POWER
        vy = math.sin(angle) * AIM_POWER
        self.ball = Ball(base[0], base[1], vx, vy)
        self.balls_left -= 1
        self.last_hit_colors = []
        sfx.launch()  # <--- NEW        

    def update(self):
        dt = 1.0/max(1, FPS)
        if self.state != "playing":
            return
        self.bucket.update()
        # Update ball
        if self.ball and self.ball.active:
            events = self.ball.update()   # <--- CHANGED (captures events)
            # play bounce SFX
            for e in events:
                if e in ("bounce_wall", "bounce_top"):
                    sfx.wall()

            # collisions with pegs
            for peg in self.pegs:
                if peg.active and ball_peg_collision(self.ball, peg):
                    # mark hit
                    peg.hit_flash = 1.0
                    self.score += 10 if peg.color==BLUE else 25 if peg.color==GREEN else 100 if peg.orange else 10
                    self.last_hit_colors.append(peg.color)
                    # SFX for peg hit
                    sfx.peg(peg.color)  # <--- NEW
                    # particles
                    for _ in range(10):
                        angle = random.uniform(0, 2*math.pi)
                        speed = random.uniform(1, 4)
                        self.particles.append(Particle(peg.x, peg.y, math.cos(angle)*speed, math.sin(angle)*speed, 0.8, peg.color))
                    # deactivate peg
                    peg.active = False
            # ground / out of bounds
            if self.ball.y > HEIGHT + 40:
                # check bucket catch for extra ball
                brect = self.bucket.rect()
                caught = False
                if len(self.ball.trail) > 0:
                    tx, ty = self.ball.trail[-1]
                    if brect.left < tx < brect.right:
                        caught = True
                if caught:
                    self.balls_left += 1
                    self.score += 250
                    sfx.bucket()  # <--- NEW
                    # confetti
                    for _ in range(40):
                        angle = random.uniform(-math.pi, 0)
                        speed = random.uniform(2, 6)
                        self.particles.append(Particle(brect.centerx, brect.top, math.cos(angle)*speed, math.sin(angle)*speed, 1.2, GREEN))
                self.ball.active = False
                self.ball = None
                # end-of-turn small bonus for combos
                if len(self.last_hit_colors) >= 3:
                    self.score += 100 * (len(self.last_hit_colors)-2)
        # update pegs
        for peg in self.pegs:
            peg.update(dt)
        # update particles
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        # check win/lose
        orange_left = sum(1 for p in self.pegs if p.active and p.orange)
        if orange_left == 0 and self.state == "playing":
            self.state = "win"
            self.score += 1000
        elif self.balls_left == 0 and self.ball is None and orange_left > 0:
            self.state = "lose"

    def draw(self):
        draw_background(screen)
        draw_bouncers(screen)
        # pegs
        for peg in self.pegs:
            peg.draw(screen)
        # bucket
        self.bucket.draw(screen)
        # ball
        if self.ball:
            self.ball.draw(screen)
        # particles
        for p in self.particles:
            p.draw(screen)
        # cannon / aim line
        mouse = pygame.mouse.get_pos()
        base = (WIDTH//2, 90)
        dx = mouse[0]-base[0]
        dy = mouse[1]-base[1]
        self.aim_angle = math.atan2(dy, dx)   # full 360° aiming
        draw_cannon(screen, base, self.aim_angle)
        aiming = (self.ball is None)
        angle_line = (base, (base[0] + int(math.cos(self.aim_angle)*120), base[1] + int(math.sin(self.aim_angle)*120)))
        orange_left = sum(1 for p in self.pegs if p.active and p.orange)
        draw_hud(screen, self.balls_left, self.score, orange_left, aiming, angle_line if aiming else None)

        # end states banners
        if self.state in ("win","lose"):
            text = "YOU ESCAPED THE HAUNTED BOARD!" if self.state=="win" else "THE CURSE REMAINS..."
            color = GREEN if self.state=="win" else RED
            s = headline_font.render(text, True, color)
            screen.blit(s, (WIDTH//2 - s.get_width()//2, HEIGHT//2-40))
            sub = font.render("Press R to restart", True, WHITE)
            screen.blit(sub, (WIDTH//2 - sub.get_width()//2, HEIGHT//2+24))

    def update_music(self):
        if self.level == 1 and not self.music_started:
            # play_halloween_music()
            self.music_started = True


# --- Main loop ---
async def main():
    print(np.array([1, 2]))
    game = Game()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_r:
                    game.reset()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                game.launch_ball(game.aim_angle)
            elif event.type == pygame.USEREVENT + 5:
                # second note of the launch chirp
                snd = sfx._tone(freq=560, ms=40, volume=0.25, shape="sine")
                if snd: snd.play()
            elif event.type == pygame.USEREVENT + 6:
                # second chime of bucket ding
                snd = sfx._tone(freq=1320, ms=75, volume=0.26, shape="sine")
                if snd: snd.play()
        game.update_music()


        game.update()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)
        await asyncio.sleep(0)

    pygame.quit()
    sys.exit()


asyncio.run(main())
