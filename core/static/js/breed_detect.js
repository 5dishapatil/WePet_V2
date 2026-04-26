/**
 * breed_detect.js — AJAX breed auto-detection for WePet Django.
 * Handles the "Don't know" species flow in pet_owner.html.
 * Calls /pets/detect-breed/ with the uploaded image and handles all result states:
 *   ok | unsupported_profile | unknown | error
 */

function handleImageUpload(inputEl) {
    if (!inputEl.files || !inputEl.files[0]) return;

    var file = inputEl.files[0];

    // Show spinner, hide previous result
    var spinner = document.getElementById('detect-spinner');
    var resultBanner = document.getElementById('detect-result-banner');
    var fallbackSection = document.getElementById('fallback-section');
    var hiddenBreed = document.getElementById('breed_name_hidden');

    if (spinner) spinner.style.display = '';
    if (resultBanner) resultBanner.style.display = 'none';
    if (fallbackSection) fallbackSection.style.display = 'none';
    if (hiddenBreed) hiddenBreed.value = '';

    var formData = new FormData();
    formData.append('pet_image', file);
    formData.append('csrfmiddlewaretoken', getCsrfToken());

    fetch('/pets/detect-breed/', {
        method: 'POST',
        body: formData
    })
    .then(function (response) {
        if (!response.ok) {
            return response.text().then(function (text) {
                throw new Error('Server returned ' + response.status + '. ' + text.slice(0, 120));
            });
        }
        return response.json();
    })
    .then(function (data) {
        if (spinner) spinner.style.display = 'none';
        handleDetectResult(data);
    })
    .catch(function (err) {
        if (spinner) spinner.style.display = 'none';
        showDetectBanner(
            'error',
            '❌ Detection failed: ' + err.message + '. Please select a species and breed manually.'
        );
        showFallbackSection('Dog');
    });
}

function handleDetectResult(data) {
    var status = data.status || 'error';

    if (status === 'ok') {
        var species = data.species || 'Dog';
        var breed   = data.mapped_profile_breed || '';
        var conf    = Math.round((data.confidence || 0) * 100);

        // 1) Force main species selector to the detected species
        var speciesSelect = document.getElementById('species_select');
        if (speciesSelect) {
            speciesSelect.value = species;

            // This switches UI from "Don't know" mode back to known-breed mode
            if (typeof handleSpeciesChange === 'function') {
                handleSpeciesChange();
            }
        }

        // 2) Ensure the visible breed dropdown contains the detected breed and select it
        var breedSelect = document.getElementById('breed_select');
        if (breedSelect) {
            var found = false;
            for (var i = 0; i < breedSelect.options.length; i++) {
                if (breedSelect.options[i].value === breed) {
                    breedSelect.value = breed;
                    found = true;
                    break;
                }
            }

            // 3) Always sync hidden field (this is what Django actually receives)
            if (typeof syncBreedHidden === 'function') {
                syncBreedHidden(found ? breedSelect.value : breed);
            } else {
                var hiddenBreed = document.getElementById('breed_name_hidden');
                if (hiddenBreed) hiddenBreed.value = breed;
            }
        } else {
            var hiddenBreed2 = document.getElementById('breed_name_hidden');
            if (hiddenBreed2) hiddenBreed2.value = breed;
        }

        // Hide fallback if it was previously shown
        var fallbackSection = document.getElementById('fallback-section');
        if (fallbackSection) fallbackSection.style.display = 'none';

        showDetectBanner(
            'info',
            '✔ Detected: ' + species + ' · ' + breed + ' (' + conf + '% confidence)'
        );

    } else if (status === 'unsupported_profile') {
        var sp2    = data.species || 'Dog';
        var disp2  = data.display_breed || data.model_breed || 'Unknown';
        var conf2  = Math.round((data.confidence || 0) * 100);

        // Set species even if profile isn't supported
        var speciesSelect2 = document.getElementById('species_select');
        if (speciesSelect2) {
            speciesSelect2.value = "Don't know"; // keep unknown flow visible
        }

        showDetectBanner(
            'info',
            'ℹ️ Detected: ' + sp2 + ' · ' + disp2 + ' (' + conf2 + '%). ' +
            'This breed is recognised but not yet supported by weather-risk profiles. ' +
            'Please choose the closest supported breed below.'
        );

        showFallbackSection(sp2);

    } else if (status === 'unknown') {
        showDetectBanner(
            'error',
            '❌ Could not confidently identify the pet. ' +
            'Please upload a clearer image or choose a breed manually below.'
        );
        showFallbackSection('Dog');

    } else {
        showDetectBanner(
            'error',
            '❌ ' + (data.message || 'Detection failed. Please select a breed manually.')
        );
        showFallbackSection('Dog');
    }
}

function showFallbackSection(defaultSpecies) {
    var section = document.getElementById('fallback-section');
    if (!section) return;

    section.style.display = '';

    var speciesSel = document.getElementById('fallback_species');
    if (speciesSel) {
        speciesSel.value = defaultSpecies || 'Dog';

        // IMPORTANT: use the GLOBAL function from pet_owner.html
        if (typeof handleFallbackSpecies === 'function') {
            handleFallbackSpecies(speciesSel.value);
        }
    }
}

function showDetectBanner(type, msg) {
    var el = document.getElementById('detect-result-banner');
    if (!el) return;

    el.style.display = '';
    el.className = (type === 'error') ? 'error-banner' : 'info-banner';
    el.textContent = msg;
}

function getCsrfToken() {
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var c = cookies[i].trim();
        if (c.startsWith('csrftoken=')) {
            return c.substring('csrftoken='.length);
        }
    }

    // Fallback: read from hidden input
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
}