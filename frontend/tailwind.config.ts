import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class", "class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
  	extend: {
  		container: {
  			center: true,
  			padding: '2rem',
  			screens: {
  				'2xl': '1400px'
  			}
  		},
  		fontFamily: {
  			sans: [
  				'var(--font-sans)',
  				'system-ui',
  				'sans-serif'
  			],
  			mono: [
  				'var(--font-mono)',
  				'ui-monospace',
  				'monospace'
  			]
  		},
  		transitionTimingFunction: {
  			'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
  			spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)'
  		},
  		boxShadow: {
  			card: 'inset 0 1px 0 0 hsl(0 0% 100% / 0.08), 0 1px 3px hsl(var(--foreground) / 0.04), 0 8px 24px -12px hsl(var(--foreground) / 0.12)',
  			'3d-card': 'inset 0 1px 0 0 hsl(0 0% 100% / 0.08), 0 2px 4px hsl(var(--foreground) / 0.05), 0 12px 32px -12px hsl(var(--foreground) / 0.16)',
  			'3d-elevated': 'inset 0 1px 0 0 hsl(0 0% 100% / 0.12), 0 4px 16px -4px hsl(var(--primary) / 0.15), 0 20px 48px -16px hsl(var(--foreground) / 0.22)',
  			'3d-floating': 'inset 0 1px 0 0 hsl(0 0% 100% / 0.15), 0 24px 60px -16px hsl(var(--foreground) / 0.35)',
  			'3d-pressed': 'inset 0 2px 4px 0 hsl(0 0% 0% / 0.2)',
  			diffuse: '0 24px 60px -24px hsl(var(--foreground) / 0.18)',
  			'inner-edge': 'inset 0 1px 0 0 hsl(0 0% 100% / 0.08)'
  		},
  		keyframes: {
  			'fade-in': {
  				'0%': {
  					opacity: '0'
  				},
  				'100%': {
  					opacity: '1'
  				}
  			},
  			'slide-up': {
  				'0%': {
  					opacity: '0',
  					transform: 'translateY(14px) scale(0.99)'
  				},
  				'100%': {
  					opacity: '1',
  					transform: 'translateY(0) scale(1)'
  				}
  			},
  			'scale-in': {
  				'0%': {
  					opacity: '0',
  					transform: 'scale(0.96)'
  				},
  				'100%': {
  					opacity: '1',
  					transform: 'scale(1)'
  				}
  			},
  			'pulse-soft': {
  				'0%, 100%': {
  					opacity: '1'
  				},
  				'50%': {
  					opacity: '0.45'
  				}
  			},
  			shimmer: {
  				'0%': {
  					backgroundPosition: '200% 0'
  				},
  				'100%': {
  					backgroundPosition: '-200% 0'
  				}
  			}
  		},
  		animation: {
  			'fade-in': 'fade-in 0.45s var(--ease-out-expo) both',
  			'slide-up': 'slide-up 0.45s var(--ease-out-expo) both',
  			'scale-in': 'scale-in 0.35s var(--ease-out-expo) both',
  			'pulse-soft': 'pulse-soft 2.4s ease-in-out infinite',
  			shimmer: 'shimmer 1.4s ease-in-out infinite'
  		},
  		colors: {
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			success: {
  				DEFAULT: 'hsl(var(--success))',
  				foreground: 'hsl(var(--success-foreground))'
  			},
  			warning: {
  				DEFAULT: 'hsl(var(--warning))',
  				foreground: 'hsl(var(--warning-foreground))'
  			},
  			info: {
  				DEFAULT: 'hsl(var(--info))',
  				foreground: 'hsl(var(--info-foreground))'
  			},
  			sidebar: {
  				DEFAULT: 'hsl(var(--sidebar-background))',
  				foreground: 'hsl(var(--sidebar-foreground))',
  				primary: 'hsl(var(--sidebar-primary))',
  				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
  				accent: 'hsl(var(--sidebar-accent))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
  				border: 'hsl(var(--sidebar-border))',
  				ring: 'hsl(var(--sidebar-ring))'
  			}
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
