# FamilyBot Price Enhancement Plan

**Document Version**: 1.0  
**Created**: June 28, 2025  
**Status**: Planning Phase  

## 🎯 Overview & Goals

This document outlines the phased enhancement plan for FamilyBot's price data collection system using the Steam library (`solsticegamestudios/steam`) to improve both Steam Store API and ITAD (IsThereAnyDeal) data coverage.

### **Primary Objectives**

- Improve Steam price data coverage from ~75% to ~90%
- Enhance ITAD historical price coverage from ~60% to ~75%
- Maintain existing functionality while adding robust fallback mechanisms
- Implement comprehensive error handling and source tracking

### **Key Benefits**

- Better price data for delisted, region-locked, and problematic games
- More reliable price collection with multiple fallback strategies
- Enhanced debugging and monitoring capabilities
- Improved user experience with more complete pricing information

---

## 📊 Current State Analysis

### **Current populate_prices.py Architecture**

```text
Steam Price Collection:
App ID → Steam Store API → Cache Game Details

ITAD Price Collection:
App ID → ITAD Lookup → ITAD Game ID → ITAD StoreLow API → Cache ITAD Price
```

### **Current Limitations**

#### **Steam Price Collection**

- **Single Point of Failure**: Only uses Steam Store API
- **Limited Coverage**: Games without store pages get no price data
- **No Fallback**: API failures result in complete data loss
- **Missing Games**: Delisted, beta, region-locked games not covered

#### **ITAD Price Collection**

- **App ID Dependency**: Relies entirely on ITAD recognizing Steam App IDs
- **No Alternative Lookup**: No fallback when App ID lookup fails
- **Name Matching Issues**: Some games have different names between Steam and ITAD
- **Limited Recovery**: Failed lookups are marked as "not found" permanently

### **Success Rate Estimates**

- **Steam Store API**: ~75% success rate
- **ITAD Lookup**: ~60% success rate
- **Combined Coverage**: ~45% of games have both Steam and ITAD data

---

## 🚀 Phased Implementation Plan

### **Phase 1: Enhanced Steam Library Fallback**

**Target Version**: v1.0.4  
**Timeline**: Immediate implementation  
**Risk Level**: Low  

#### **Scope**

- Add Steam library as fallback for Steam Store API failures
- Implement price source tracking in database
- Enhanced logging and error handling
- No changes to existing primary logic

#### **Implementation Strategy**

```text
Enhanced Steam Price Flow:
App ID → Steam Store API (existing)
       ↓ (if fails)
       → Steam Library WebAPI → Basic Price Data
       ↓ (if fails)
       → Steam Library App Details → Package Price Data
       ↓ (if fails)
       → Mark as failed with detailed error tracking
```

#### **Database Changes**

```sql
-- Add price source tracking
ALTER TABLE game_details_cache ADD COLUMN price_source TEXT DEFAULT 'store_api';

-- Possible values: 'store_api', 'steam_library', 'package_lookup', 'failed'
```

#### **Expected Outcomes**

- Steam price success rate: 75% → 90%
- Better coverage for delisted games
- Enhanced debugging capabilities
- No breaking changes

---

### **Phase 2: Enhanced ITAD Game Identification**

**Target Version**: v1.0.5  
**Timeline**: After Phase 1 completion and testing  
**Risk Level**: Medium  

#### **Phase 2 Scope**

- Steam library assisted ITAD game identification
- ITAD name-based search fallback
- Enhanced ITAD lookup method tracking
- Cross-reference Steam and ITAD game data

#### **Phase 2 Implementation Strategy**

```text
Enhanced ITAD Price Flow:
App ID → ITAD App ID Lookup (existing)
       ↓ (if fails)
       → Steam Library Game Info → Enhanced Game Metadata
       ↓
       → ITAD Name Search → Alternative Game Identification
       ↓ (if found)
       → ITAD StoreLow API → Cache with Enhanced Metadata
```

#### **Phase 2 Database Changes**

```sql
-- Add ITAD lookup method tracking
ALTER TABLE itad_price_cache ADD COLUMN lookup_method TEXT DEFAULT 'appid';

-- Possible values: 'appid', 'name_search', 'steam_library_assisted'
ALTER TABLE itad_price_cache ADD COLUMN steam_game_name TEXT;
```

#### **Phase 2 Expected Outcomes**

- ITAD success rate: 60% → 75%
- Better historical price coverage
- Enhanced game name matching
- Improved fallback strategies

---

### **Phase 3: Advanced Integration & Optimization**

**Target Version**: v1.0.6  
**Timeline**: After Phase 2 completion and validation  
**Risk Level**: Low (polish and optimization)  

#### **Phase 3 Scope**

- Cross-validation between Steam and ITAD data
- Performance optimizations and caching improvements
- Advanced error handling and retry logic
- Comprehensive monitoring and analytics

#### **Phase 3 Implementation Strategy**

- Smart price validation and conflict resolution
- Enhanced regional pricing support
- Advanced caching strategies
- Production-ready monitoring and alerting

#### **Phase 3 Expected Outcomes**

- Maximum data quality and coverage
- Production-ready reliability
- Enhanced performance and monitoring
- Comprehensive error tracking

---

## 🛠️ Technical Implementation Details

### **Phase 1: Steam Library Integration**

#### **New Methods to Implement**

```python
def fetch_steam_price_enhanced(self, app_id: str) -> tuple[str, bool, str]:
    """Enhanced Steam price fetching with Steam library fallback."""
    
    # Strategy 1: Current Steam Store API (keep existing)
    success, source = self.fetch_steam_store_price(app_id)
    if success:
        return app_id, True, 'store_api'
    
    # Strategy 2: Steam library WebAPI fallback
    success, source = self.fetch_steam_library_price(app_id)
    if success:
        return app_id, True, 'steam_library'
    
    # Strategy 3: Steam library package lookup
    success, source = self.fetch_steam_package_price(app_id)
    if success:
        return app_id, True, 'package_lookup'
    
    return app_id, False, 'failed'

def fetch_steam_library_price(self, app_id: str) -> tuple[bool, str]:
    """Use Steam library WebAPI as fallback for price data."""
    try:
        from steam.webapi import WebAPI
        
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            logger.debug(f"Steam library fallback skipped for {app_id}: No API key")
            return False, 'no_api_key'
        
        api = WebAPI(key=STEAMWORKS_API_KEY)
        
        # Try to get app info using Steam library
        try:
            # Get app list and find our app
            app_list = api.call('ISteamApps.GetAppList')
            if app_list and 'applist' in app_list:
                for app in app_list['applist']['apps']:
                    if str(app.get('appid')) == app_id:
                        # Found the app, create basic game data
                        game_data = {
                            'name': app['name'],
                            'type': 'game',
                            'is_free': False,  # Default assumption
                            'categories': [],
                            'price_overview': None  # No price data from app list
                        }
                        
                        # Cache the basic game details
                        cache_game_details_with_source(app_id, game_data, 'steam_library')
                        logger.debug(f"Steam library fallback successful for app {app_id}: {app['name']}")
                        return True, 'steam_library'
                        
        except Exception as e:
            logger.debug(f"Steam library WebAPI call failed for {app_id}: {e}")
            return False, 'webapi_error'
        
        logger.debug(f"Steam library fallback: app {app_id} not found in app list")
        return False, 'not_found'
        
    except ImportError:
        logger.debug("Steam library not available for fallback")
        return False, 'library_unavailable'
    except Exception as e:
        logger.debug(f"Steam library fallback failed for {app_id}: {e}")
        return False, 'library_error'

def fetch_steam_package_price(self, app_id: str) -> tuple[bool, str]:
    """Use Steam library for package-based price lookup."""
    try:
        from steam.webapi import WebAPI
        
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            return False, 'no_api_key'
        
        api = WebAPI(key=STEAMWORKS_API_KEY)
        
        # Try to get package information for the app
        # This is more advanced and may require additional Steam library features
        # Implementation depends on available Steam library capabilities
        
        logger.debug(f"Steam package lookup attempted for app {app_id}")
        return False, 'not_implemented'  # Placeholder for future implementation
        
    except ImportError:
        return False, 'library_unavailable'
    except Exception as e:
        logger.debug(f"Steam package lookup failed for {app_id}: {e}")
        return False, 'package_error'

def cache_game_details_with_source(self, app_id: str, game_data: dict, source: str):
    """Enhanced cache_game_details with source tracking."""
    # Call existing cache_game_details but with source parameter
    cache_game_details(app_id, game_data, permanent=True)
    
    # Update the price_source field
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE game_details_cache SET price_source = ? WHERE appid = ?",
            (source, app_id)
        )
        conn.commit()
        conn.close()
        logger.debug(f"Updated price source for {app_id}: {source}")
    except Exception as e:
        logger.error(f"Failed to update price source for {app_id}: {e}")
```

#### **Phase 1 Database Migration Script**

```python
def migrate_database_phase1():
    """Add price_source column to game_details_cache table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(game_details_cache)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'price_source' not in columns:
            cursor.execute("ALTER TABLE game_details_cache ADD COLUMN price_source TEXT DEFAULT 'store_api'")
            
            # Update existing entries to have 'store_api' as source
            cursor.execute("UPDATE game_details_cache SET price_source = 'store_api' WHERE price_source IS NULL")
            
            conn.commit()
            logger.info("Phase 1 database migration completed: Added price_source column")
        else:
            logger.info("Phase 1 database migration skipped: price_source column already exists")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Phase 1 database migration failed: {e}")
        raise
```

### **Phase 2: ITAD Enhancement**

#### **ITAD Enhancement Methods**

```python
def fetch_itad_price_enhanced(self, app_id: str) -> tuple[str, str]:
    """Enhanced ITAD fetching with Steam library assistance."""
    
    # Strategy 1: Current ITAD App ID lookup (keep existing)
    result = self.fetch_itad_by_appid(app_id)
    if result == "cached":
        return app_id, result
    
    # Strategy 2: Steam library assisted game identification
    game_info = self.get_steam_library_game_info(app_id)
    if game_info and game_info.get('name'):
        result = self.fetch_itad_by_name(app_id, game_info['name'])
        if result == "cached":
            return app_id, result
    
    # Strategy 3: Enhanced name variations (future)
    # Could try alternative names, remove subtitles, etc.
    
    return app_id, "not_found"

def get_steam_library_game_info(self, app_id: str) -> Optional[dict]:
    """Get enhanced game info from Steam library for ITAD matching."""
    try:
        from steam.webapi import WebAPI
        
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            return None
        
        api = WebAPI(key=STEAMWORKS_API_KEY)
        
        # Get app list and find our app
        app_list = api.call('ISteamApps.GetAppList')
        if app_list and 'applist' in app_list:
            for app in app_list['applist']['apps']:
                if str(app.get('appid')) == app_id:
                    return {
                        'name': app['name'],
                        'appid': app['appid']
                    }
        
        return None
        
    except Exception as e:
        logger.debug(f"Steam library game info failed for {app_id}: {e}")
        return None

def fetch_itad_by_name(self, app_id: str, game_name: str) -> str:
    """Try ITAD lookup by game name when App ID lookup fails."""
    try:
        # Use ITAD search API to find game by name
        search_url = f"https://api.isthereanydeal.com/games/search/v1?key={ITAD_API_KEY}&title={game_name}"
        
        search_response = self.make_request_with_retry(search_url, method="GET", api_type="itad")
        if search_response is None:
            return "error"
        
        search_data = self.handle_api_response(f"ITAD Search ({game_name})", search_response)
        if not search_data or not search_data.get('games'):
            return "not_found"
        
        # Take the first match (most relevant)
        game_id = search_data['games'][0].get('id')
        if not game_id:
            return "not_found"
        
        # Now get price data using the found game ID
        storelow_url = f"https://api.isthereanydeal.com/games/storelow/v2?key={ITAD_API_KEY}&country=US&shops=61"
        storelow_response = self.make_request_with_retry(storelow_url, method="POST", json_data=[game_id], api_type="itad")
        
        if storelow_response is None:
            return "error"
        
        storelow_data = self.handle_api_response(f"ITAD StoreLow ({game_name})", storelow_response)
        
        if storelow_data and storelow_data[0].get("lows"):
            low = storelow_data[0]["lows"][0]
            
            # Cache with enhanced metadata
            cache_itad_price_enhanced(app_id, {
                'lowest_price': str(low["price"]["amount"]), 
                'lowest_price_formatted': f"${low['price']['amount']}", 
                'shop_name': low.get("shop", {}).get("name", "Unknown Store")
            }, lookup_method='name_search', steam_game_name=game_name)
            
            return "cached"
        else:
            return "not_found"
            
    except Exception as e:
        logger.error(f"ITAD name search failed for {game_name}: {e}")
        return "error"
```

---

## 📋 Success Metrics & Testing

### **Phase 1 Success Criteria**

- [ ] Steam price success rate improves by at least 10%
- [ ] No regression in existing functionality
- [ ] Database migration completes successfully
- [ ] Price source tracking works correctly
- [ ] Enhanced logging provides useful debugging info
- [ ] Steam library fallback activates when Store API fails

### **Phase 2 Success Criteria**

- [ ] ITAD success rate improves by at least 10%
- [ ] Name-based ITAD search works correctly
- [ ] Steam library game identification functions properly
- [ ] ITAD lookup method tracking works
- [ ] No impact on existing ITAD functionality

### **Testing Strategy**

#### **Unit Tests**

```python
def test_steam_library_fallback():
    """Test Steam library fallback functionality."""
    # Mock Steam Store API failure
    # Verify Steam library fallback activates
    # Check price_source is set correctly

def test_itad_name_search():
    """Test ITAD name-based search fallback."""
    # Mock ITAD App ID lookup failure
    # Verify name search activates
    # Check lookup_method is set correctly

def test_database_migrations():
    """Test database schema migrations."""
    # Verify new columns are added correctly
    # Test migration idempotency
    # Validate data integrity
```

#### **Integration Tests**

```python
def test_end_to_end_price_collection():
    """Test complete price collection workflow."""
    # Test with various game types
    # Verify fallback chains work correctly
    # Check data quality and completeness

def test_performance_impact():
    """Verify performance doesn't degrade."""
    # Measure execution time before/after
    # Check memory usage
    # Validate rate limiting still works
```

---

## ⚠️ Risk Assessment & Mitigation

### **Phase 1 Risks**

#### **Risk**: Steam library dependency issues

**Probability**: Medium  
**Impact**: Medium  
**Mitigation**:

- Graceful fallback when Steam library unavailable
- Comprehensive error handling
- Optional dependency pattern

#### **Risk**: Database migration failures

**Probability**: Low  
**Impact**: High  
**Mitigation**:

- Test migrations on backup database
- Implement rollback procedures
- Validate schema before deployment

#### **Risk**: Performance degradation

**Probability**: Low  
**Impact**: Medium  
**Mitigation**:

- Fallbacks only activate on primary failures
- Maintain existing rate limiting
- Monitor execution times

### **Phase 2 Risks**

#### **Risk**: ITAD API rate limiting

**Probability**: Medium  
**Impact**: Medium  
**Mitigation**:

- Implement additional rate limiting for name searches
- Cache search results to avoid repeated lookups
- Graceful degradation when rate limited

#### **Risk**: Name matching accuracy

**Probability**: Medium  
**Impact**: Low  
**Mitigation**:

- Use exact name matches initially
- Implement fuzzy matching carefully
- Log mismatches for analysis

---

## 🔄 Version Tracking & Commits

### **Phase 1 Commit Strategy**

```bash
# Database migration
git commit -m "feat: add price source tracking to game cache schema"

# Steam library integration
git commit -m "feat: add Steam library fallback for price collection"

# Enhanced logging
git commit -m "feat: enhance price collection logging and error handling"

# Final phase commit
git commit -m "feat: complete Phase 1 Steam library price enhancement

- Add Steam library fallback for failed Store API calls
- Implement price source tracking in database
- Enhanced error handling and logging
- Improve price data coverage for delisted games

Version: v1.0.4"
```

### **Phase 2 Commit Strategy**

```bash
# ITAD enhancements
git commit -m "feat: enhance ITAD lookup with Steam library assistance"

# Name-based search
git commit -m "feat: add ITAD name-based search fallback"

# Final phase commit
git commit -m "feat: complete Phase 2 ITAD enhancement

- Add Steam library assisted ITAD game identification
- Implement name-based ITAD search fallback
- Enhanced ITAD lookup method tracking
- Improve historical price data coverage

Version: v1.0.5"
```

---

## 🔮 Future Considerations

### **Potential Phase 4: Advanced Features**

- Regional pricing support
- Price history tracking and trends
- Smart price validation and conflict resolution
- Enhanced caching strategies
- Real-time price monitoring

### **Monitoring & Analytics**

- Success rate dashboards
- Performance metrics tracking
- Error pattern analysis
- Data quality monitoring

### **Scalability Considerations**

- Async processing for large datasets
- Distributed caching strategies
- API quota management
- Load balancing for multiple data sources

---

## 📚 References & Documentation

### **Related Documents**

- [VERSION_MANAGEMENT.md](./VERSION_MANAGEMENT.md) - Version bumping and release management
- [WEB_UI_README.md](./WEB_UI_README.md) - Web interface documentation
- [ROADMAP.md](./ROADMAP.md) - Project roadmap and future plans

### **External APIs**

- [Steam Web API Documentation](https://steamcommunity.com/dev)
- [IsThereAnyDeal API Documentation](https://docs.isthereanydeal.com/)
- [Steam Library Documentation](https://github.com/solsticegamestudios/steam)

### **Implementation Files**

- `scripts/populate_prices.py` - Main price collection script
- `src/familybot/lib/database.py` - Database operations
- `src/familybot/lib/logging_config.py` - Logging configuration

---

**Document Status**: Ready for Implementation  
**Next Action**: Begin Phase 1 implementation  
**Estimated Timeline**: Phase 1 (1-2 days), Phase 2 (2-3 days), Phase 3 (1-2 days)
