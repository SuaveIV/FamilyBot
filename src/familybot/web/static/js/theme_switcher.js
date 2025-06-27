/**
 * FamilyBot Theme Switcher
 * Handles Bootstrap/Bootswatch theme switching with localStorage persistence
 */

class ThemeSwitcher {
    constructor() {
        this.themes = {
            'default': {
                name: 'Bootstrap Default',
                url: 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
                preview: '#0d6efd'
            },
            'cerulean': {
                name: 'Cerulean',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/cerulean/bootstrap.min.css',
                preview: '#2FA4E7'
            },
            'cosmo': {
                name: 'Cosmo',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/cosmo/bootstrap.min.css',
                preview: '#2780E3'
            },
            'flatly': {
                name: 'Flatly',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/flatly/bootstrap.min.css',
                preview: '#18BC9C'
            },
            'journal': {
                name: 'Journal',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/journal/bootstrap.min.css',
                preview: '#EB6864'
            },
            'litera': {
                name: 'Litera',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/litera/bootstrap.min.css',
                preview: '#4582EC'
            },
            'lumen': {
                name: 'Lumen',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/lumen/bootstrap.min.css',
                preview: '#158CBA'
            },
            'minty': {
                name: 'Minty',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/minty/bootstrap.min.css',
                preview: '#78C2AD'
            },
            'pulse': {
                name: 'Pulse',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/pulse/bootstrap.min.css',
                preview: '#593196'
            },
            'sandstone': {
                name: 'Sandstone',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/sandstone/bootstrap.min.css',
                preview: '#93C54B'
            },
            'united': {
                name: 'United',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/united/bootstrap.min.css',
                preview: '#E95420'
            },
            'yeti': {
                name: 'Yeti',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/yeti/bootstrap.min.css',
                preview: '#008CBA'
            },
            // Dark themes
            'cyborg': {
                name: 'Cyborg (Dark)',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/cyborg/bootstrap.min.css',
                preview: '#2A9FD6',
                dark: true
            },
            'darkly': {
                name: 'Darkly (Dark)',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/darkly/bootstrap.min.css',
                preview: '#375A7F',
                dark: true
            },
            'slate': {
                name: 'Slate (Dark)',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/slate/bootstrap.min.css',
                preview: '#272B30',
                dark: true
            },
            'solar': {
                name: 'Solar (Dark)',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/solar/bootstrap.min.css',
                preview: '#B58900',
                dark: true
            },
            'superhero': {
                name: 'Superhero (Dark)',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/superhero/bootstrap.min.css',
                preview: '#DF691A',
                dark: true
            },
            'vapor': {
                name: 'Vapor (Dark)',
                url: 'https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/vapor/bootstrap.min.css',
                preview: '#EA39B8',
                dark: true
            }
        };
        
        this.currentTheme = 'default';
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
        
        // Load saved theme or use default
        const savedTheme = localStorage.getItem(this.storageKey);
        if (savedTheme && this.themes[savedTheme]) {
            this.setTheme(savedTheme);
        } else {
            this.setTheme('default');
        }
        
        // Initialize theme selector if it exists
        this.initThemeSelector();
        
        // Listen for system theme changes
        this.initSystemThemeListener();
    }
    
    setTheme(themeKey) {
        if (!this.themes[themeKey]) {
            console.warn(`Theme '${themeKey}' not found, using default`);
            themeKey = 'default';
        }
        
        const theme = this.themes[themeKey];
        this.currentTheme = themeKey;
        
        // Update the CSS link
        this.themeLink.href = theme.url;
        
        // Update data-bs-theme attribute for Bootstrap 5.3+ dark mode support
        if (theme.dark) {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
        } else {
            document.documentElement.setAttribute('data-bs-theme', 'light');
        }
        
        // Save to localStorage
        localStorage.setItem(this.storageKey, themeKey);
        
        // Update theme selector if it exists
        this.updateThemeSelector();
        
        // Dispatch custom event
        document.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { theme: themeKey, themeData: theme }
        }));
        
        console.log(`Theme changed to: ${theme.name}`);
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
        
        // Add light themes section
        const lightHeader = document.createElement('h6');
        lightHeader.className = 'dropdown-header';
        lightHeader.textContent = 'Light Themes';
        dropdownMenu.appendChild(lightHeader);
        
        Object.entries(this.themes).forEach(([key, theme]) => {
            if (!theme.dark) {
                const item = this.createDropdownItem(key, theme);
                dropdownMenu.appendChild(item);
            }
        });
        
        // Add divider
        const divider = document.createElement('hr');
        divider.className = 'dropdown-divider';
        dropdownMenu.appendChild(divider);
        
        // Add dark themes section
        const darkHeader = document.createElement('h6');
        darkHeader.className = 'dropdown-header';
        darkHeader.textContent = 'Dark Themes';
        dropdownMenu.appendChild(darkHeader);
        
        Object.entries(this.themes).forEach(([key, theme]) => {
            if (theme.dark) {
                const item = this.createDropdownItem(key, theme);
                dropdownMenu.appendChild(item);
            }
        });
    }
    
    createDropdownItem(key, theme) {
        const item = document.createElement('a');
        item.className = 'dropdown-item d-flex align-items-center';
        item.href = '#';
        item.innerHTML = `
            <span class="theme-preview me-2" style="background-color: ${theme.preview}"></span>
            ${theme.name}
            ${key === this.currentTheme ? '<i class="fas fa-check ms-auto"></i>' : ''}
        `;
        
        item.addEventListener('click', (e) => {
            e.preventDefault();
            this.setTheme(key);
        });
        
        return item;
    }
    
    updateThemeSelector() {
        const selector = document.getElementById('theme-selector');
        if (selector) {
            selector.value = this.currentTheme;
        }
        
        // Update dropdown if it exists
        this.initThemeDropdown();
    }
    
    initSystemThemeListener() {
        // Listen for system theme changes
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addEventListener('change', (e) => {
                // Only auto-switch if user hasn't manually selected a theme
                const savedTheme = localStorage.getItem(this.storageKey);
                if (!savedTheme) {
                    if (e.matches) {
                        this.setTheme('darkly'); // Default dark theme
                    } else {
                        this.setTheme('default'); // Default light theme
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
            this.setTheme('default');
        } else {
            this.setTheme('darkly');
        }
    }
}

// Initialize theme switcher when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.themeSwitcher = new ThemeSwitcher();
    
    // Initialize dropdown if it exists
    setTimeout(() => {
        window.themeSwitcher.initThemeDropdown();
    }, 100);
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeSwitcher;
}
