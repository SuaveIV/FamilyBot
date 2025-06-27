/**
 * FamilyBot Simplified Theme Switcher
 * Focuses on reliable, usable themes with consistent styling
 */

class ThemeSwitcher {
    constructor() {
        // Simplified theme list with only reliable, well-tested themes
        this.themes = {
            'light': {
                name: 'Light Mode',
                url: 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
                preview: '#0d6efd',
                dark: false
            },
            'dark': {
                name: 'Dark Mode',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/darkly/bootstrap.min.css',
                preview: '#375A7F',
                dark: true
            },
            'blue': {
                name: 'Blue Theme',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/cerulean/bootstrap.min.css',
                preview: '#2FA4E7',
                dark: false
            },
            'green': {
                name: 'Green Theme',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/flatly/bootstrap.min.css',
                preview: '#18BC9C',
                dark: false
            }
        };
        
        this.currentTheme = 'light';
        this.themeLink = null;
        this.storageKey = 'familybot-theme';
        
        this.init();
    }
    
    init() {
        // Create or find the theme link element
        this.themeLink = document.getElementById('theme-css');
        if (!this.themeLink) {
            this.themeLink = document.createElement('link');
            this.themeLink.id = 'theme-css';
            this.themeLink.rel = 'stylesheet';
            document.head.appendChild(this.themeLink);
        }
        
        // Load saved theme or detect system preference
        const savedTheme = localStorage.getItem(this.storageKey);
        if (savedTheme && this.themes[savedTheme]) {
            this.setTheme(savedTheme);
        } else {
            // Auto-detect system preference
            this.detectSystemTheme();
        }
        
        // Initialize theme controls
        this.initThemeControls();
        
        // Listen for system theme changes
        this.initSystemThemeListener();
    }
    
    detectSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            this.setTheme('dark');
        } else {
            this.setTheme('light');
        }
    }
    
    setTheme(themeKey) {
        if (!this.themes[themeKey]) {
            console.warn(`Theme '${themeKey}' not found, using light theme`);
            themeKey = 'light';
        }
        
        const theme = this.themes[themeKey];
        this.currentTheme = themeKey;
        
        // Update the CSS link with error handling
        this.themeLink.href = theme.url;
        
        // Handle theme loading errors
        this.themeLink.onerror = () => {
            console.error(`Failed to load theme: ${theme.name}`);
            if (themeKey !== 'light') {
                // Fallback to light theme if current theme fails to load
                this.setTheme('light');
            }
        };
        
        // Update data-bs-theme attribute for Bootstrap 5.3+ dark mode support
        document.documentElement.setAttribute('data-bs-theme', theme.dark ? 'dark' : 'light');
        
        // Add theme class to body for additional styling
        document.body.className = document.body.className.replace(/theme-\w+/g, '');
        document.body.classList.add(`theme-${themeKey}`);
        
        // Save to localStorage
        localStorage.setItem(this.storageKey, themeKey);
        
        // Update theme controls
        this.updateThemeControls();
        
        // Dispatch custom event
        document.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { theme: themeKey, themeData: theme }
        }));
        
        console.log(`Theme changed to: ${theme.name}`);
    }
    
    initThemeControls() {
        // Initialize dropdown if it exists
        setTimeout(() => {
            this.initThemeDropdown();
        }, 100);
        
        // Initialize selector if it exists
        this.initThemeSelector();
    }
    
    initThemeSelector() {
        const selector = document.getElementById('theme-selector');
        if (!selector) return;
        
        // Clear existing options
        selector.innerHTML = '';
        
        // Add theme options
        Object.entries(this.themes).forEach(([key, theme]) => {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = theme.name;
            if (key === this.currentTheme) {
                option.selected = true;
            }
            selector.appendChild(option);
        });
        
        // Add change listener
        selector.addEventListener('change', (e) => {
            this.setTheme(e.target.value);
        });
    }
    
    initThemeDropdown() {
        const dropdown = document.getElementById('theme-dropdown');
        if (!dropdown) return;
        
        const dropdownMenu = dropdown.querySelector('.dropdown-menu');
        if (!dropdownMenu) return;
        
        // Clear existing items
        dropdownMenu.innerHTML = '';
        
        // Add theme options
        Object.entries(this.themes).forEach(([key, theme]) => {
            const item = this.createDropdownItem(key, theme);
            dropdownMenu.appendChild(item);
        });
        
        // Add divider and quick toggle
        const divider = document.createElement('hr');
        divider.className = 'dropdown-divider';
        dropdownMenu.appendChild(divider);
        
        // Add quick dark mode toggle
        const toggleItem = document.createElement('a');
        toggleItem.className = 'dropdown-item d-flex align-items-center';
        toggleItem.href = '#';
        toggleItem.innerHTML = `
            <i class="fas fa-adjust me-2"></i>
            Toggle Dark Mode
        `;
        toggleItem.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleDarkMode();
        });
        dropdownMenu.appendChild(toggleItem);
    }
    
    createDropdownItem(key, theme) {
        const item = document.createElement('a');
        item.className = 'dropdown-item d-flex align-items-center';
        item.href = '#';
        
        const isActive = key === this.currentTheme;
        item.innerHTML = `
            <span class="theme-preview me-2" style="background-color: ${theme.preview}; width: 16px; height: 16px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1);"></span>
            ${theme.name}
            ${isActive ? '<i class="fas fa-check ms-auto text-success"></i>' : ''}
        `;
        
        if (isActive) {
            item.classList.add('active');
        }
        
        item.addEventListener('click', (e) => {
            e.preventDefault();
            this.setTheme(key);
        });
        
        return item;
    }
    
    updateThemeControls() {
        // Update selector
        const selector = document.getElementById('theme-selector');
        if (selector) {
            selector.value = this.currentTheme;
        }
        
        // Update dropdown
        this.initThemeDropdown();
    }
    
    initSystemThemeListener() {
        // Listen for system theme changes
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addEventListener('change', (e) => {
                // Only auto-switch if user hasn't manually selected a theme recently
                const savedTheme = localStorage.getItem(this.storageKey);
                const lastChanged = localStorage.getItem(this.storageKey + '-timestamp');
                const now = Date.now();
                
                // If no saved theme or last change was more than 1 hour ago, follow system preference
                if (!savedTheme || !lastChanged || (now - parseInt(lastChanged)) > 3600000) {
                    if (e.matches) {
                        this.setTheme('dark');
                    } else {
                        this.setTheme('light');
                    }
                }
            });
        }
    }
    
    getCurrentTheme() {
        return {
            key: this.currentTheme,
            data: this.themes[this.currentTheme]
        };
    }
    
    getAvailableThemes() {
        return this.themes;
    }
    
    isDarkTheme() {
        return this.themes[this.currentTheme]?.dark || false;
    }
    
    // Utility method to toggle between light and dark
    toggleDarkMode() {
        if (this.isDarkTheme()) {
            this.setTheme('light');
        } else {
            this.setTheme('dark');
        }
        
        // Mark as manually changed
        localStorage.setItem(this.storageKey + '-timestamp', Date.now().toString());
    }
    
    // Method to reset to system preference
    resetToSystemTheme() {
        localStorage.removeItem(this.storageKey);
        localStorage.removeItem(this.storageKey + '-timestamp');
        this.detectSystemTheme();
    }
}

// Initialize theme switcher when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.themeSwitcher = new ThemeSwitcher();
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeSwitcher;
}
