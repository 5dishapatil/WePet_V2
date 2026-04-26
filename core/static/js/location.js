/**
 * location.js — Browser GPS geolocation for WePet Django.
 * FINAL VERSION for current WePet system.
 *
 * Features:
 * - Auto-fetch location on page load if GPS mode is selected AND permission already granted
 * - No need for user to click "Get Current Location" every time
 * - Manual refresh still supported
 * - Reverse geocode via OpenStreetMap Nominatim
 * - Safe fallback to coordinates if reverse geocode fails
 * - Keeps compatibility with current pet_owner.html hidden fields:
 *      geo_lat, geo_lon, location_label
 * - Uses existing banner IDs:
 *      gps-info-banner, gps-success-banner, gps-error-banner
 * - Uses existing button IDs:
 *      get-location-btn, refresh-location-btn
 */

var _locationLocked = false;
var _locationInProgress = false;
var _locationAutoTried = false;

document.addEventListener('DOMContentLoaded', function () {
    initialiseLocationUX();
});

/* ─────────────────────────────────────────────────────────────
   INITIAL SETUP
───────────────────────────────────────────────────────────── */
function initialiseLocationUX() {
    var gpsRadio = document.getElementById('gps_radio');
    if (!gpsRadio) return;

    // If GPS mode already selected on page load, set UI correctly
    if (gpsRadio.checked) {
        syncLocationModeUI(true);

        // If hidden fields already have location, don't fetch again
        var lat = getElValue('geo_lat');
        var lon = getElValue('geo_lon');
        var label = getElValue('location_label');

        if (lat && lon) {
            _locationLocked = true;
            toggleLocationButtons(true);

            if (label) {
                showGpsSuccess('📍 Using current location: ' + label);
            } else {
                showGpsSuccess('📍 Using current location: ' + Number(lat).toFixed(4) + ', ' + Number(lon).toFixed(4));
            }
            return;
        }

        // Try auto-fetch only if permission already granted
        tryAutoFetchLocation();
    } else {
        syncLocationModeUI(false);
    }
}

/* ─────────────────────────────────────────────────────────────
   MODE SWITCH HANDLER (called from pet_owner.html radio onchange)
───────────────────────────────────────────────────────────── */
function handleLocationMode() {
    var isGps = !!(document.getElementById('gps_radio') && document.getElementById('gps_radio').checked);

    syncLocationModeUI(isGps);

    if (!isGps) {
        hideGpsBanners();
        return;
    }

    // If already have location, don't ask again
    var lat = getElValue('geo_lat');
    var lon = getElValue('geo_lon');
    var label = getElValue('location_label');

    if (lat && lon) {
        _locationLocked = true;
        toggleLocationButtons(true);

        if (label) {
            showGpsSuccess('📍 Using current location: ' + label);
        } else {
            showGpsSuccess('📍 Using current location: ' + Number(lat).toFixed(4) + ', ' + Number(lon).toFixed(4));
        }
        return;
    }

    // If permission already granted, auto-fetch
    tryAutoFetchLocation();
}

/* ─────────────────────────────────────────────────────────────
   AUTO FETCH IF PERMISSION ALREADY GRANTED
───────────────────────────────────────────────────────────── */
function tryAutoFetchLocation() {
    if (_locationAutoTried || _locationLocked || _locationInProgress) return;
    _locationAutoTried = true;

    if (!navigator.geolocation) return;

    // Best UX: check permission first if browser supports it
    if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'geolocation' })
            .then(function (permissionStatus) {
                if (permissionStatus.state === 'granted') {
                    requestLocation(true); // auto mode
                } else {
                    // Not granted yet — user can click manually
                    toggleLocationButtons(false);
                }

                // If user grants later while page is open
                permissionStatus.onchange = function () {
                    if (permissionStatus.state === 'granted' && !_locationLocked && !_locationInProgress) {
                        requestLocation(true);
                    }
                };
            })
            .catch(function () {
                // If permissions API fails, do nothing automatically
                toggleLocationButtons(false);
            });
    } else {
        // Older browser: don't auto-trigger permission popup unexpectedly
        toggleLocationButtons(false);
    }
}

/* ─────────────────────────────────────────────────────────────
   MAIN LOCATION REQUEST
   requestLocation() still works for button onclick
───────────────────────────────────────────────────────────── */
function requestLocation(isAuto) {
    if (typeof isAuto === 'undefined') isAuto = false;

    if (!navigator.geolocation) {
        showGpsError('Browser geolocation is not supported. Please enter your location manually.');
        return;
    }

    if (_locationInProgress) return;
    _locationInProgress = true;

    var btn = document.getElementById('get-location-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = isAuto ? '⏳ Detecting automatically…' : '⏳ Locating…';
    }

    hideGpsBanners();

    var infoBanner = document.getElementById('gps-info-banner');
    if (infoBanner) {
        infoBanner.style.display = '';
        infoBanner.textContent = isAuto
            ? '⏳ Detecting your current location automatically…'
            : '⏳ Requesting GPS location…';
    }

    navigator.geolocation.getCurrentPosition(
        function (position) {
            var lat = position.coords.latitude;
            var lon = position.coords.longitude;

            setLocationFields(lat, lon);
            _locationLocked = true;

            // Show immediate feedback
            showGpsSuccess('📍 Location captured: ' + lat.toFixed(4) + ', ' + lon.toFixed(4));

            // Update buttons immediately
            toggleLocationButtons(true);
            resetGetLocationButton();

            // Reverse geocode via OSM for a friendly label
            reverseGeocodeOSM(lat, lon, function (label) {
                setLocationLabel(label);
                showGpsSuccess('📍 Location: ' + label);
                _locationInProgress = false;
            });
        },
        function (err) {
            var msg = '';
            switch (err.code) {
                case err.PERMISSION_DENIED:
                    msg = 'Location access denied. Please allow location permission or enter your city manually.';
                    break;
                case err.POSITION_UNAVAILABLE:
                    msg = 'Location unavailable. Please try again or enter your city manually.';
                    break;
                case err.TIMEOUT:
                    msg = 'Location request timed out. Please try again.';
                    break;
                default:
                    msg = 'Could not get location. Please enter your city manually.';
            }

            showGpsError(msg);
            toggleLocationButtons(false);
            resetGetLocationButton();
            _locationInProgress = false;
        },
        {
            timeout: 10000,
            maximumAge: 300000,   // 5 minutes cached location is okay for this use-case
            enableHighAccuracy: false
        }
    );
}

/* ─────────────────────────────────────────────────────────────
   MANUAL REFRESH
───────────────────────────────────────────────────────────── */
function refreshLocation() {
    _locationLocked = false;
    _locationInProgress = false;
    _locationAutoTried = false;

    setLocationFields('', '');
    setLocationLabel('');

    toggleLocationButtons(false);
    hideGpsBanners();

    requestLocation(false);
}

/* ─────────────────────────────────────────────────────────────
   REVERSE GEOCODING (OpenStreetMap Nominatim)
───────────────────────────────────────────────────────────── */
function reverseGeocodeOSM(lat, lon, callback) {
    var url =
        'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=' +
        encodeURIComponent(lat) +
        '&lon=' +
        encodeURIComponent(lon) +
        '&zoom=12&addressdetails=1';

    fetch(url, {
        headers: {
            'Accept': 'application/json'
        }
    })
        .then(function (r) {
            if (!r.ok) throw new Error('Reverse geocoding failed');
            return r.json();
        })
        .then(function (data) {
            var addr = data.address || {};
            var parts = [];

            var locality =
                addr.city ||
                addr.town ||
                addr.village ||
                addr.suburb ||
                addr.county;

            if (locality) parts.push(locality);
            if (addr.state && parts.indexOf(addr.state) < 0) parts.push(addr.state);
            if (addr.country && parts.indexOf(addr.country) < 0) parts.push(addr.country);

            var label = parts.length
                ? parts.join(', ')
                : (data.display_name || 'Current Location');

            callback(label);
        })
        .catch(function () {
            // Safe fallback
            callback(Number(lat).toFixed(4) + ', ' + Number(lon).toFixed(4));
        });
}

/* ─────────────────────────────────────────────────────────────
   UI HELPERS
───────────────────────────────────────────────────────────── */
function syncLocationModeUI(isGps) {
    var gpsSection = document.getElementById('gps-section');
    var manualSection = document.getElementById('manual-section');

    if (gpsSection) gpsSection.style.display = isGps ? '' : 'none';
    if (manualSection) manualSection.style.display = isGps ? 'none' : '';

    if (!isGps) return;

    var lat = getElValue('geo_lat');
    var lon = getElValue('geo_lon');

    toggleLocationButtons(!!(lat && lon));
}

function toggleLocationButtons(hasLocation) {
    var getBtn = document.getElementById('get-location-btn');
    var refreshBtn = document.getElementById('refresh-location-btn');

    if (getBtn) getBtn.style.display = hasLocation ? 'none' : '';
    if (refreshBtn) refreshBtn.style.display = hasLocation ? '' : 'none';
}

function resetGetLocationButton() {
    var btn = document.getElementById('get-location-btn');
    if (btn) {
        btn.disabled = false;
        btn.textContent = '📍 Get Current Location';
    }
}

function setLocationFields(lat, lon) {
    var latEl = document.getElementById('geo_lat');
    var lonEl = document.getElementById('geo_lon');

    if (latEl) latEl.value = lat;
    if (lonEl) lonEl.value = lon;
}

function setLocationLabel(label) {
    var labelEl = document.getElementById('location_label');
    if (labelEl) labelEl.value = label || '';
}

function getElValue(id) {
    var el = document.getElementById(id);
    return el ? (el.value || '').trim() : '';
}

/* ─────────────────────────────────────────────────────────────
   BANNERS
───────────────────────────────────────────────────────────── */
function showGpsSuccess(msg) {
    hideGpsBanners();
    var el = document.getElementById('gps-success-banner');
    if (el) {
        el.textContent = msg;
        el.style.display = '';
    }
}

function showGpsError(msg) {
    hideGpsBanners();
    var el = document.getElementById('gps-error-banner');
    if (el) {
        el.textContent = '❌ ' + msg;
        el.style.display = '';
    }
}

function hideGpsBanners() {
    ['gps-info-banner', 'gps-success-banner', 'gps-error-banner'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
}