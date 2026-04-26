/**
 * ngo_breed_detect.js — AJAX breed auto-detection for NGO registry.
 * Uses /ngo/detect-breed/
 * Supports:
 *   ok | unsupported_profile | unknown | error
 */

function handleNgoImageUpload(inputEl) {
    if (!inputEl.files || !inputEl.files[0]) return;

    var file = inputEl.files[0];

    var spinner = document.getElementById('ngo-detect-spinner');
    var banner = document.getElementById('ngo-detect-result-banner');
    var fallback = document.getElementById('ngo-fallback-section');

    if (spinner) spinner.style.display = '';
    if (banner) banner.style.display = 'none';
    if (fallback) fallback.style.display = 'none';

    setNgoDetectedValues('', '');

    var formData = new FormData();
    formData.append('pet_image', file);
    formData.append('csrfmiddlewaretoken', getNgoCsrfToken());

    fetch('/ngo/detect-breed/', {
        method: 'POST',
        body: formData
    })
    .then(function (r) {
        return r.json();
    })
    .then(function (data) {
        if (spinner) spinner.style.display = 'none';
        handleNgoDetectResult(data);
    })
    .catch(function (err) {
        if (spinner) spinner.style.display = 'none';
        showNgoDetectBanner(
            'error',
            '❌ Detection failed: ' + err.message + '. Please choose the breed manually below.'
        );
        showNgoFallbackSection('Dog');
    });
}

function handleNgoDetectResult(data) {
    var status = data.status || 'error';

    if (status === 'ok') {
        var species = data.species || 'Dog';
        var breed = data.mapped_profile_breed || '';
        var conf = Math.round((data.confidence || 0) * 100);

        showNgoDetectBanner(
            'info',
            '✔ Detected: ' + species + ' · ' + breed + ' (' + conf + '% confidence)'
        );

        setNgoDetectedValues(species, breed);
        syncNgoFormFromDetected(species, breed);

    } else if (status === 'unsupported_profile') {
        var sp2 = data.species || 'Dog';
        var disp2 = data.display_breed || data.model_breed || 'Unknown';
        var conf2 = Math.round((data.confidence || 0) * 100);

        showNgoDetectBanner(
            'info',
            'ℹ️ Detected: ' + sp2 + ' · ' + disp2 + ' (' + conf2 + '%). ' +
            'This breed is recognised but not yet supported by climate profiles. ' +
            'Please choose the closest supported breed manually below.'
        );

        setNgoDetectedValues('', '');
        showNgoFallbackSection(sp2);

    } else if (status === 'unknown') {
        showNgoDetectBanner(
            'error',
            '❌ Could not confidently identify the animal. Please upload a clearer image or choose manually below.'
        );

        setNgoDetectedValues('', '');
        showNgoFallbackSection('Dog');

    } else {
        showNgoDetectBanner(
            'error',
            '❌ ' + (data.message || 'Detection failed. Please choose a breed manually below.')
        );

        setNgoDetectedValues('', '');
        showNgoFallbackSection('Dog');
    }
}

function setNgoDetectedValues(species, breed) {
    var speciesHidden = document.getElementById('ngo_detected_species');
    var breedHidden = document.getElementById('ngo_detected_breed');

    if (speciesHidden) speciesHidden.value = species || '';
    if (breedHidden) breedHidden.value = breed || '';
}

function syncNgoFormFromDetected(species, breed) {
    var speciesSel = document.getElementById('id_species');
    var breedSel = document.getElementById('id_breed_name');

    if (speciesSel && species) {
        speciesSel.value = species;
        handleNgoSpeciesChange(species);
    }

    if (breedSel && breed) {
        // wait until options repopulate
        setTimeout(function () {
            breedSel.value = breed;
        }, 10);
    }
}

function showNgoFallbackSection(defaultSpecies) {
    var section = document.getElementById('ngo-fallback-section');
    if (!section) return;

    section.style.display = '';

    var speciesSel = document.getElementById('id_species');
    if (speciesSel) {
        speciesSel.value = defaultSpecies || 'Dog';
        handleNgoSpeciesChange(speciesSel.value);
    }
}

function handleNgoSpeciesChange(species) {
    var breedSel = document.getElementById('id_breed_name');
    if (!breedSel) return;

    var breeds = (species === 'Cat') ? NGO_CAT_BREEDS : NGO_DOG_BREEDS;

    breedSel.innerHTML = '';

    var placeholder = new Option('Select breed', '');
    breedSel.appendChild(placeholder);

    breeds.forEach(function (b) {
        var opt = new Option(b, b);
        breedSel.appendChild(opt);
    });

    // If manual change occurs, clear detected values to avoid stale override
    setNgoDetectedValues('', '');
}

function showNgoDetectBanner(type, msg) {
    var el = document.getElementById('ngo-detect-result-banner');
    if (!el) return;

    el.style.display = '';
    el.className = (type === 'error') ? 'error-banner' : 'info-banner';
    el.textContent = msg;
}

function getNgoCsrfToken() {
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var c = cookies[i].trim();
        if (c.startsWith('csrftoken=')) {
            return c.substring('csrftoken='.length);
        }
    }

    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
}