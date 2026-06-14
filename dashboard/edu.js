document.addEventListener('DOMContentLoaded', () => {
  if (!window.MACRO_DATA || !window.MACRO_DATA.theory) {
    document.getElementById('empty-state').innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i><h2>Lỗi Dữ Liệu</h2><p>Không tìm thấy dữ liệu MACRO_DATA.theory. Vui lòng chạy lại script build_dashboard.py.</p>';
    return;
  }

  const theoryData = window.MACRO_DATA.theory;
  const releasesHistory = window.MACRO_DATA.releases_history || {};
  
  // Lấy danh sách các ngày có dữ liệu và sắp xếp giảm dần
  const availableDates = Object.keys(releasesHistory).sort().reverse();
  
  const sidebar = document.getElementById('sidebar-content');
  const emptyState = document.getElementById('empty-state');
  const contentCard = document.getElementById('content-card');
  const dateSelector = document.getElementById('date-selector');

  // DOM Elements for Content
  const elShortName = document.getElementById('ind-short-name');
  const elFullName = document.getElementById('ind-full-name');
  const elDeepDiveLink = document.getElementById('ind-deep-dive-link');
  const elNewsLink = document.getElementById('ind-news-link');
  const elPrimaryLink = document.getElementById('ind-primary-link');
  const elLink = document.getElementById('ind-link');
  const elDesc = document.getElementById('ind-desc');
  const elFreq = document.getElementById('ind-freq');
  const elLatestRelease = document.getElementById('ind-latest-release');
  const elExpect = document.getElementById('ind-expect');
  const elGoodBad = document.getElementById('ind-good-bad');
  const elMarketReaction = document.getElementById('ind-market-reaction');
  
  // DOM Elements for Release Info
  const elReleaseInfo = document.getElementById('release-info-alert');
  const elRelDate = document.getElementById('rel-date');
  const elRelActual = document.getElementById('rel-actual');
  const elRelForecast = document.getElementById('rel-forecast');
  const elRelPrev = document.getElementById('rel-previous');
  const elRelSurprise = document.getElementById('rel-surprise');

  let activeItem = null;
  let currentDate = availableDates.length > 0 ? availableDates[0] : null;

  // Initialize Date Selector
  if (availableDates.length > 0) {
    availableDates.forEach(date => {
      const option = document.createElement('option');
      option.value = date;
      option.textContent = date;
      dateSelector.appendChild(option);
    });
    dateSelector.value = currentDate;
    
    dateSelector.addEventListener('change', (e) => {
      currentDate = e.target.value;
      renderSidebar();
      // Nếu đang mở 1 chỉ số, cập nhật lại phần release info
      if (activeItem) {
        const indicatorId = activeItem.dataset.id;
        const indicator = findIndicatorById(indicatorId);
        if (indicator) {
          updateReleaseInfo(indicator);
        }
      }
    });
  } else {
    dateSelector.parentElement.style.display = 'none';
  }

  function findIndicatorById(id) {
    for (const cat of theoryData.categories) {
      const ind = cat.indicators.find(i => i.id === id);
      if (ind) return ind;
    }
    return null;
  }

  // Hàm helper để match indicator với release name
  function matchRelease(indicator, releases) {
    const shortName = (indicator.short_name || '').toLowerCase();
    const fullName = (indicator.full_name || '').toLowerCase();
    
    // Tìm release nào có tên chứa short_name hoặc full_name
    return releases.find(r => {
      const rName = r.name.toLowerCase();
      // Xử lý một số case đặc biệt (ví dụ: NFP -> Nonfarm, Jobless Claims)
      if (shortName === 'nfp' && rName.includes('nonfarm')) return true;
      if (shortName === 'jobless claims' && rName.includes('initial jobless claims')) return true;
      if (shortName === 'cpi' && rName.includes('cpi') && !rName.includes('core')) return true;
      if (shortName === 'core cpi' && rName.includes('core cpi')) return true;
      if (shortName === 'ppi' && rName.includes('ppi') && !rName.includes('core') && !rName.includes('ex.')) return true;
      if (shortName === 'core ppi' && rName.includes('core ppi')) return true;
      if (shortName === 'gdp' && rName.includes('gdp')) return true;
      
      return rName.includes(shortName) || (fullName && rName.includes(fullName));
    });
  }

  function renderSidebar() {
    sidebar.innerHTML = '';
    const currentReleases = releasesHistory[currentDate] || [];

    theoryData.categories.forEach(category => {
      const catDiv = document.createElement('div');
      catDiv.className = 'category';

      const catTitle = document.createElement('div');
      catTitle.className = 'category-title';
      catTitle.textContent = category.name;
      catDiv.appendChild(catTitle);

      const indList = document.createElement('div');
      indList.className = 'indicator-list';

      category.indicators.forEach(indicator => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'indicator-item';
        itemDiv.dataset.id = indicator.id;
        
        // Kiểm tra xem chỉ số này có được công bố trong ngày đang chọn không
        const matchedRelease = matchRelease(indicator, currentReleases);
        const isReleasedToday = !!matchedRelease;

        if (isReleasedToday) {
          itemDiv.classList.add('today');
        }
        
        // Giữ state active nếu đang chọn
        if (activeItem && activeItem.dataset.id === indicator.id) {
          itemDiv.classList.add('active');
          activeItem = itemDiv;
        }

        const nameSpan = document.createElement('span');
        nameSpan.className = 'indicator-name';
        nameSpan.textContent = indicator.short_name;
        
        itemDiv.appendChild(nameSpan);

        if (isReleasedToday) {
          const badge = document.createElement('span');
          badge.className = 'indicator-badge';
          badge.textContent = 'Công bố ngày này';
          itemDiv.appendChild(badge);
        }

        // Handle Click
        itemDiv.addEventListener('click', () => {
          if (activeItem) {
            activeItem.classList.remove('active');
          }
          itemDiv.classList.add('active');
          activeItem = itemDiv;
          
          showIndicatorContent(indicator);
        });

        indList.appendChild(itemDiv);
      });

      catDiv.appendChild(indList);
      sidebar.appendChild(catDiv);
    });
  }

  function classifySurprise(actualStr, forecastStr) {
    if (!actualStr || !forecastStr) return { label: "—", cls: "surprise-inline" };
    const a = parseFloat(actualStr.replace(/[%,KMB]/g, ""));
    const f = parseFloat(forecastStr.replace(/[%,KMB]/g, ""));
    if (isNaN(a) || isNaN(f)) return { label: "—", cls: "surprise-inline" };
    if (Math.abs(a - f) < Math.max(0.05, Math.abs(f) * 0.02)) return { label: "in-line", cls: "surprise-inline" };
    return a > f ? { label: "beat", cls: "surprise-beat" } : { label: "miss", cls: "surprise-miss" };
  }

  function updateReleaseInfo(indicator) {
    const currentReleases = releasesHistory[currentDate] || [];
    const matchedRelease = matchRelease(indicator, currentReleases);

    if (matchedRelease) {
      elRelDate.textContent = currentDate;
      
      elRelActual.textContent = matchedRelease.actual || "—";
      elRelForecast.textContent = matchedRelease.forecast || "—";
      elRelPrev.textContent = matchedRelease.previous || "—";
      
      const surprise = classifySurprise(matchedRelease.actual, matchedRelease.forecast);
      elRelSurprise.textContent = surprise.label.toUpperCase();
      elRelSurprise.className = surprise.cls;
      
      // Update actual color based on surprise
      elRelActual.className = 'actual-val';
      if (surprise.label === 'beat') elRelActual.classList.add('beat');
      if (surprise.label === 'miss') elRelActual.classList.add('miss');

      elReleaseInfo.style.display = 'block';
    } else {
      elReleaseInfo.style.display = 'none';
    }
  }

  function findLatestReleaseDate(indicator) {
    const dates = Object.keys(releasesHistory).sort().reverse();
    for (const date of dates) {
      if (matchRelease(indicator, releasesHistory[date])) {
        return date;
      }
    }
    return null;
  }

  function showIndicatorContent(indicator) {
    emptyState.style.display = 'none';
    
    // Cuộn main content lên đầu
    document.getElementById('main-content').scrollTop = 0;
    
    // Reset animation
    contentCard.style.animation = 'none';
    contentCard.offsetHeight; // trigger reflow
    contentCard.style.animation = null;
    
    contentCard.style.display = 'block';

    elShortName.textContent = indicator.short_name;
    elFullName.textContent = indicator.full_name;
    
    if (indicator.deep_dive_link) {
      elDeepDiveLink.href = indicator.deep_dive_link;
      elDeepDiveLink.style.display = 'inline-block';
    } else {
      elDeepDiveLink.style.display = 'none';
    }

    if (indicator.news_release_link) {
      elNewsLink.href = indicator.news_release_link;
      elNewsLink.style.display = 'inline-block';
    } else {
      elNewsLink.style.display = 'none';
    }
    
    if (indicator.primary_link) {
      elPrimaryLink.href = indicator.primary_link;
      elPrimaryLink.style.display = 'inline-block';
    } else {
      elPrimaryLink.style.display = 'none';
    }
    
    elLink.href = indicator.link;
    elDesc.textContent = indicator.description;
    elFreq.textContent = indicator.frequency;
    
    const latestDate = findLatestReleaseDate(indicator);
    const fredDate = window.MACRO_DATA.fred_history?.fred_snapshot?.[indicator.id]?.latest?.date;
    
    if (latestDate) {
      elLatestRelease.innerHTML = `<i class="fa-solid fa-clock-rotate-left"></i> Công bố gần nhất: ${latestDate}`;
    } else if (fredDate) {
      // Convert YYYY-MM-DD to MM/YYYY
      const parts = fredDate.split('-');
      const formattedFred = parts.length === 3 ? `${parts[1]}/${parts[0]}` : fredDate;
      elLatestRelease.innerHTML = `<i class="fa-solid fa-clock-rotate-left"></i> Kỳ dữ liệu gần nhất: Tháng ${formattedFred} (Theo FRED)`;
    } else {
      elLatestRelease.textContent = "";
    }

    elExpect.textContent = indicator.expectation_meaning;
    elGoodBad.textContent = indicator.good_vs_bad;

    if (indicator.market_reaction) {
      elMarketReaction.textContent = indicator.market_reaction;
      elMarketReaction.parentElement.parentElement.style.display = 'block';
    } else {
      elMarketReaction.textContent = '';
      elMarketReaction.parentElement.parentElement.style.display = 'none';
    }

    // ====== NEW FIELDS: read_format / watch_thresholds / release_pattern / related_indicators ======
    const readFmtSection = document.getElementById('section-read-format');
    const readFmtEl = document.getElementById('ind-read-format');
    if (indicator.read_format) {
      readFmtEl.innerHTML = markdownLite(indicator.read_format);
      readFmtSection.style.display = '';
    } else {
      readFmtSection.style.display = 'none';
    }

    const thresholdsSection = document.getElementById('section-thresholds-pattern');
    const watchEl = document.getElementById('ind-watch-thresholds');
    const patternEl = document.getElementById('ind-release-pattern');
    const hasWatch = !!indicator.watch_thresholds;
    const hasPattern = !!indicator.release_pattern;
    if (hasWatch || hasPattern) {
      watchEl.innerHTML = hasWatch ? markdownLite(indicator.watch_thresholds) : '<em style="color: var(--text-secondary);">—</em>';
      patternEl.innerHTML = hasPattern ? markdownLite(indicator.release_pattern) : '<em style="color: var(--text-secondary);">—</em>';
      thresholdsSection.style.display = '';
    } else {
      thresholdsSection.style.display = 'none';
    }

    const relatedSection = document.getElementById('section-related');
    const relatedEl = document.getElementById('ind-related');
    const related = (indicator.related_indicators || []).filter(Boolean);
    if (related.length) {
      relatedEl.innerHTML = related.map(id => {
        const other = findIndicatorById(id);
        const label = other ? other.short_name : id;
        return `<button class="related-chip" data-related-id="${id}">${label} <i class="fa-solid fa-arrow-right" style="font-size:0.7rem;"></i></button>`;
      }).join('');
      relatedSection.style.display = '';
      // Wire clicks
      relatedEl.querySelectorAll('.related-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.relatedId;
          const target = findIndicatorById(id);
          if (target) {
            // Update active state in sidebar
            const sidebarItem = document.querySelector(`.indicator-item[data-id="${id}"]`);
            if (sidebarItem) {
              if (activeItem) activeItem.classList.remove('active');
              sidebarItem.classList.add('active');
              activeItem = sidebarItem;
              sidebarItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            showIndicatorContent(target);
          }
        });
      });
    } else {
      relatedSection.style.display = 'none';
    }

    updateReleaseInfo(indicator);
  }

  // Minimal markdown: bold **text** + line breaks
  function markdownLite(s) {
    if (!s) return '';
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  // Initial render
  renderSidebar();
});
