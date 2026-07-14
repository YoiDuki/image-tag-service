<script>
  import { onMount } from 'svelte'
  import { getImages, getImagesByColor, getStats, getFilters, updateImage, deleteImage, getTagsMeta, addTagMeta, updateTagMeta, deleteTagMeta, getTagSynonyms, addTagSynonym, deleteTagSynonym } from './lib/api.js'

  let images = $state([])
  let stats = $state({ total: 0, pending: 0, done: 0, error: 0 })
  let filterOptions = $state({ authors: [], media_types: [], styles: [], tags: [] })
  let filters = $state({
    author: '',
    media_type: '',
    style: '',
    tag: '',
    nsfw: '',
    search: '',
    sort: 'updated_at',
  })
  let colorPick = $state('#888888')
  let colorThreshold = $state(100)
  let colorActive = $state(false)
  let page = $state(1)
  let pageInfo = $state({ page: 1, per_page: 24, total: 0, total_pages: 0 })
  let search = $state('')
let searchTimer = $state(null)
  let loading = $state(true)
  let selectedImage = $state(null)
  let editingTags = $state('')
  let saving = $state(false)
  let allLoaded = $state(false)
  let loadingMore = $state(false)
  let sentinelEl = $state(null)
  let rescanMode = $state(false)
  let selectedForRescan = $state(new Set())
  let rescanning = $state(false)
  let showTagManager = $state(false)
  let tagManagerTags = $state([])
  let tagManagerSearch = $state('')
  let tagManagerNew = $state('')
  let tagManagerDesc = $state('')
  let tagManagerEditing = $state(null)
  let tagManagerEditDesc = $state('')
  let tagFilterFocused = $state(false)
  let authorFilterFocused = $state(false)

  const filteredAuthorOptions = $derived(
    filters.author
      ? filterOptions.authors.filter(a => a.name.toLowerCase().includes(filters.author.toLowerCase()))
      : filterOptions.authors
  )

  const synonymMap = $derived(filterOptions.synonym_map || {})

  function resolveTag(tag) {
    return synonymMap[tag] || tag
  }

  const resolvedTagsAll = $derived(
    (() => {
      const map = {}
      for (const t of filterOptions.tags) {
        const canonical = synonymMap[t.name] || t.name
        if (!map[canonical]) map[canonical] = { name: canonical, count: 0 }
        map[canonical].count += t.count
      }
      return Object.values(map).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    })()
  )

  const resolvedTagsFiltered = $derived(
    tagFilter
      ? resolvedTagsAll.filter(t => t.name.toLowerCase().includes(tagFilter.toLowerCase()))
      : resolvedTagsAll
  )

  const resolvedTagNames = $derived(resolvedTagsAll.map(t => t.name))

  const resolvedTagsFilteredNames = $derived(resolvedTagsFiltered.map(t => t.name))

  let tagSynonyms = $state([])
  let synonymSearch = $state('')
  let synonymNew = $state('')
  let synonymCanonical = $state('')

  async function loadTagManager() {
    tagManagerTags = await getTagsMeta(tagManagerSearch || undefined)
  }

  async function loadSynonyms() {
    tagSynonyms = await getTagSynonyms(synonymSearch || undefined)
  }

  async function addSynonym() {
    const syn = synonymNew.trim()
    const can = synonymCanonical.trim()
    if (!syn || !can) return
    await addTagSynonym(syn, can)
    synonymNew = ''
    synonymCanonical = ''
    await loadSynonyms()
  }

  async function deleteSynonym(syn) {
    await deleteTagSynonym(syn)
    await loadSynonyms()
  }

  async function addTagManagerTag() {
    const name = tagManagerNew.trim()
    if (!name) return
    await addTagMeta(name, tagManagerDesc.trim())
    tagManagerNew = ''
    tagManagerDesc = ''
    await loadTagManager()
    await loadFilterOptions()
  }

  async function saveTagManagerEdit(name) {
    await updateTagMeta(name, tagManagerEditDesc.trim())
    tagManagerEditing = null
    tagManagerEditDesc = ''
    await loadTagManager()
  }

  async function deleteTagManagerTag(name) {
    if (!confirm(`Delete tag "${name}"?`)) return
    await deleteTagMeta(name)
    await loadTagManager()
    await loadFilterOptions()
  }

  function hexToRgb(hex) {
    const h = hex.replace('#', '')
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    }
  }

  async function loadImages() {
    loading = true
    allLoaded = false
    page = 1
    try {
      let res
      if (colorActive && colorPick) {
        const { r, g, b } = hexToRgb(colorPick)
        res = await getImagesByColor(r, g, b, colorThreshold, 1)
      } else {
        res = await getImages({ ...filters, search }, 1)
      }
      images = res.images
      pageInfo = res
      page = 1
      allLoaded = res.page >= res.total_pages
    } catch (e) {
      console.error('Failed to load images:', e)
    } finally {
      loading = false
    }
  }

  async function loadMore() {
    if (loadingMore || allLoaded) return
    loadingMore = true
    try {
      const next = page + 1
      let res
      if (colorActive && colorPick) {
        const { r, g, b } = hexToRgb(colorPick)
        res = await getImagesByColor(r, g, b, colorThreshold, next)
      } else {
        res = await getImages({ ...filters, search }, next)
      }
      images = [...images, ...res.images]
      pageInfo = res
      page = next
      allLoaded = next >= res.total_pages
    } catch (e) {
      console.error('Failed to load more:', e)
    } finally {
      loadingMore = false
    }
  }

  async function loadStats() {
    try {
      stats = await getStats()
    } catch (e) {
      console.error('Failed to load stats:', e)
    }
  }

  async function loadFilterOptions() {
    try {
      filterOptions = await getFilters()
    } catch (e) {
      console.error('Failed to load filters:', e)
    }
  }

  onMount(() => {
    loadFilterOptions()
    loadImages()
    loadStats()
  })

  function onSearchInput() {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      page = 1
      loadImages()
    }, 300)
  }

  function clearSearch() {
    search = ''
    if (searchTimer) clearTimeout(searchTimer)
    page = 1
    loadImages()
  }

  function applyFilters() {
    colorActive = false
    page = 1
    loadImages()
  }

  function applyColor(e) {
    colorPick = e.currentTarget.value
    colorActive = true
    page = 1
    loadImages()
  }

  function applyThreshold() {
    if (colorActive) {
      page = 1
      loadImages()
    }
  }

  function clearColor() {
    colorActive = false
    page = 1
    loadImages()
  }

  $effect(() => {
    const el = sentinelEl
    if (!el) return
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) loadMore()
    }, { rootMargin: '400px' })
    obs.observe(el)
    return () => obs.disconnect()
  })

  function resetFilters() {
    filters = { author: '', media_type: '', style: '', tag: '', nsfw: '', sort: 'updated_at' }
    if (searchTimer) clearTimeout(searchTimer)
    search = ''
    colorActive = false
    page = 1
    loadImages()
  }



  function openDetail(img) {
    selectedImage = img
    editingTags = JSON.stringify(img.tags || [], null, 2)
  }

  function closeDetail() {
    selectedImage = null
    editingTags = ''
  }

  async function saveTags() {
    if (!selectedImage) return
    saving = true
    try {
      let tags
      try {
        tags = JSON.parse(editingTags)
        if (!Array.isArray(tags)) throw new Error('must be array')
      } catch (e) {
        alert('Invalid JSON: ' + e.message)
        return
      }
      await updateImage(selectedImage.filename, { tags })
      await loadImages()
      await loadFilterOptions()
      selectedImage.tags = tags
    } catch (e) {
      alert('Save failed: ' + e.message)
    } finally {
      saving = false
    }
  }

  async function handleDelete(filename) {
    if (!confirm(`Delete ${filename}?`)) return
    try {
      await deleteImage(filename)
      if (selectedImage?.filename === filename) closeDetail()
      await loadImages()
      await loadStats()
      await loadFilterOptions()
    } catch (e) {
      alert('Delete failed: ' + e.message)
    }
  }

  async function handleRescan(filename) {
    try {
      await updateImage(filename, { status: 'pending' })
      await loadImages()
      await loadStats()
    } catch (e) {
      console.error('Rescan failed: ' + e.message)
    }
  }

  async function updateField(filename, field, value) {
    try {
      await updateImage(filename, { [field]: value })
      await loadFilterOptions()
    } catch (e) {
      console.error(`Failed to update ${field}:`, e)
    }
  }

  function toggleRescanMode() {
    if (rescanMode) {
      rescanMode = false
      selectedForRescan = new Set()
    } else {
      rescanMode = true
    }
  }

  function toggleSelect(filename) {
    const next = new Set(selectedForRescan)
    if (next.has(filename)) {
      next.delete(filename)
    } else {
      next.add(filename)
    }
    selectedForRescan = next
  }

  async function startRescan() {
    if (selectedForRescan.size === 0) return
    rescanning = true
    const results = await Promise.allSettled(
      [...selectedForRescan].map(filename => updateImage(filename, { status: 'pending' }))
    )
    const count = results.filter(r => r.status === 'fulfilled').length
    rescanMode = false
    selectedForRescan = new Set()
    rescanning = false
    await loadImages()
    await loadStats()
    alert(`Rescan queued for ${count} image(s). Run 'python run_tag.py process' to process.`)
  }

  function nsfwBadge(nsfw) {
    return nsfw === 'yes' ? '🔞' : ''
  }

  function statusClass(status) {
    return status === 'done' ? 'badge-done' : status === 'error' ? 'badge-error' : 'badge-pending'
  }

  function formatDate(s) {
    if (!s) return ''
    return s.length > 10 ? s.slice(0, 10) : s
  }

  function paletteStyle(palette) {
    if (!palette || !palette.length) return ''
    const stops = palette
      .map((c, i) => {
        const pos = (i / palette.length) * 100
        const nextPos = ((i + 1) / palette.length) * 100
        return `${c.hex} ${pos}% ${nextPos}%`
      })
      .join(', ')
    return `background: linear-gradient(to right, ${stops})`
  }

  let tagFilter = $state('')

  function addTag(tag) {
    let tags
    try {
      tags = JSON.parse(editingTags)
      if (!Array.isArray(tags)) tags = []
    } catch {
      tags = []
    }
    if (!tags.includes(tag)) {
      tags = [...tags, tag]
      editingTags = JSON.stringify(tags, null, 2)
    }
  }

  function removeTag(tag) {
    let tags
    try {
      tags = JSON.parse(editingTags)
      if (!Array.isArray(tags)) tags = []
    } catch {
      tags = []
    }
    tags = tags.filter(t => t !== tag)
    editingTags = JSON.stringify(tags, null, 2)
  }

  const currentTags = $derived(
    (() => {
      try {
        const t = JSON.parse(editingTags)
        return Array.isArray(t) ? t : []
      } catch {
        return []
      }
    })()
  )
</script>

<main>
  <header>
    <h1>Image Tag Service</h1>
    <div class="header-actions">
      <div class="stats">
        <span class="stat">Total: {stats.total}</span>
        <span class="stat pending">Pending: {stats.pending}</span>
        <span class="stat done">Done: {stats.done}</span>
        <span class="stat error">Error: {stats.error}</span>
      </div>
      <div class="header-buttons">
        <button class="filter-btn" class:active={rescanMode} onclick={toggleRescanMode}>
          {rescanMode ? 'Cancel' : 'Rescan'}
        </button>
        {#if rescanMode}
          <button class="filter-btn" onclick={() => selectedForRescan = new Set(images.map(i => i.filename))}>Select All</button>
          <button class="filter-btn primary" onclick={startRescan} disabled={rescanning || selectedForRescan.size === 0}>
            {rescanning ? 'Processing...' : `Start (${selectedForRescan.size})`}
          </button>
        {/if}
        <button class="filter-btn" onclick={() => { showTagManager = true; tagManagerSearch = ''; synonymSearch = ''; loadTagManager(); loadSynonyms() }}>Manage Tags</button>
      </div>
    </div>
  </header>

  <div class="toolbar">
    <div class="filters">
      <div class="tag-filter-wrap">
        <input
          type="text"
          bind:value={filters.author}
          onfocus={() => authorFilterFocused = true}
          onblur={() => setTimeout(() => authorFilterFocused = false, 150)}
          oninput={applyFilters}
          placeholder="Author: All"
          class="filter-select tag-filter-input"
        />
        {#if filters.author}
          <button class="tag-filter-clear" onclick={() => { filters.author = ''; applyFilters() }}>✕</button>
        {/if}
        {#if authorFilterFocused && filteredAuthorOptions.length > 0}
          <div class="tag-filter-dropdown">
            {#each filteredAuthorOptions.slice(0, 50) as a}
              <button class="tag-filter-option" onmousedown={() => { filters.author = a.name; applyFilters(); authorFilterFocused = false }}>{a.name} ({a.count})</button>
            {/each}
          </div>
        {/if}
      </div>
      <select bind:value={filters.nsfw} onchange={applyFilters} class="filter-select">
        <option value="">NSFW: All</option>
        <option value="no">No NSFW</option>
        <option value="yes">NSFW only</option>
      </select>
      <select bind:value={filters.media_type} onchange={applyFilters} class="filter-select">
        <option value="">Media: All</option>
        {#each filterOptions.media_types as m}
          <option value={m}>{m}</option>
        {/each}
      </select>
      <select bind:value={filters.style} onchange={applyFilters} class="filter-select">
        <option value="">Style: All</option>
        {#each filterOptions.styles as s}
          <option value={s}>{s}</option>
        {/each}
      </select>
      <div class="tag-filter-wrap">
        {#if filters.tag === '__no_tag__'}
          <span class="tag-filter-no-tag">Tag: No Tag</span>
          <button class="tag-filter-clear" onclick={() => { filters.tag = ''; applyFilters() }}>✕</button>
        {:else}
          <input
            type="text"
            bind:value={filters.tag}
            onfocus={() => tagFilterFocused = true}
            onblur={() => setTimeout(() => tagFilterFocused = false, 150)}
            oninput={applyFilters}
            placeholder="Tag: All"
            class="filter-select tag-filter-input"
          />
          {#if filters.tag}
            <button class="tag-filter-clear" onclick={() => { filters.tag = ''; applyFilters() }}>✕</button>
          {/if}
        {/if}
        {#if tagFilterFocused}
          <div class="tag-filter-dropdown">
            <button class="tag-filter-option" onmousedown={() => { filters.tag = '__no_tag__'; applyFilters(); tagFilterFocused = false }}>No Tag</button>
            {#each resolvedTagsAll.filter(t => !filters.tag || t.name.toLowerCase().includes(filters.tag.toLowerCase())).slice(0, 50) as t}
              <button class="tag-filter-option" onmousedown={() => { filters.tag = t.name; applyFilters(); tagFilterFocused = false }}>{t.name} ({t.count})</button>
            {/each}
          </div>
        {/if}
      </div>
      <button class="filter-btn" onclick={resetFilters}>Reset</button>
      <select bind:value={filters.sort} onchange={applyFilters} class="filter-select">
        <option value="updated_at">Sort: Updated</option>
        <option value="posted_at">Sort: Posted</option>
      </select>
      <span class="color-divider"></span>
      <input
        type="color"
        value={colorPick}
        onchange={applyColor}
        class="color-input"
        title="Filter by palette color"
      />
      {#if colorActive}
        <label class="threshold-label">
          <span>Δ {colorThreshold}</span>
          <input
            type="range"
            min="0"
            max="441"
            bind:value={colorThreshold}
            onchange={applyThreshold}
            class="threshold-slider"
          />
        </label>
        <button class="filter-btn" onclick={clearColor} title="Clear color filter">✕</button>
      {/if}
    </div>
    <div class="search-wrap">
      <input
        type="text"
        placeholder="Search filename, author, character, style, media..."
        bind:value={search}
        oninput={onSearchInput}
        class="search-input"
      />
      {#if search}
        <button class="search-clear" onclick={clearSearch}>✕</button>
      {/if}
    </div>
  </div>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if images.length === 0}
    <div class="empty">No images found</div>
  {:else}
    <div class="grid">
      {#each images as img (img.filename)}
        <div
          class="card"
          class:selected={selectedImage?.filename === img.filename}
          class:rescan-selected={selectedForRescan.has(img.filename)}
          onclick={() => { if (rescanMode) { toggleSelect(img.filename) } else { openDetail(img) } }}
          role="button"
          tabindex="0"
          onkeydown={(e) => e.key === 'Enter' && (rescanMode ? toggleSelect(img.filename) : openDetail(img))}
        >
          <div class="card-thumb">
            <img src="/api/images/{img.filename}/file" alt={img.filename} loading="lazy" />
            <span class="nsfw-overlay">{nsfwBadge(img.nsfw)}</span>
            {#if rescanMode}
              <span class="check-overlay">{selectedForRescan.has(img.filename) ? '✓' : ''}</span>
            {/if}
          </div>
          <div class="card-info">
            <!-- filename shown in detail panel only -->
            {#if img.author_username || img.posted_at}
              <div class="card-author">
                {#if img.author_username}<span>@{img.author_username}</span>{/if}
                {#if img.posted_at}<span class="card-date">{formatDate(img.posted_at)}</span>{/if}
              </div>
            {/if}
            <div class="card-meta">
              <!-- status shown in detail panel only -->
              {#if img.tags_edited === '1' || img.tags_edited === 1}
                <span class="badge-edited">edited</span>
              {/if}
              {#if nsfwBadge(img.nsfw)}<span class="badge-nsfw">NSFW</span>{/if}
              <span class="media-type" class:type-photo={img.media_type === 'photograph'} class:type-illust={img.media_type === 'illustration'}>{img.media_type}</span>
              {#if img.style}<span class="media-type style-tag">{img.style}</span>{/if}
            </div>
            {#if img.palette?.length}
              <div class="palette-bar" style={paletteStyle(img.palette)}></div>
            {/if}
            {#if img.tags?.length}
              <div class="card-tags">
                {#each [...new Set(img.tags.slice(0, 4).map(t => resolveTag(typeof t === 'string' ? t : t.label)))] as t}
                  <span class="tag content">{t}</span>
                {/each}
              </div>
            {/if}
            {#if img.characters?.length}
              <div class="card-tags">
                {#each img.characters.slice(0, 3) as c}
                  <span class="tag character">{c.label}</span>
                {/each}
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
    {#if !allLoaded}
      <div bind:this={sentinelEl} class="scroll-sentinel">
        {#if loadingMore}<span>Loading more…</span>{/if}
      </div>
    {/if}
  {/if}
</main>

{#if selectedImage}
  <div class="overlay" onclick={closeDetail} role="presentation"></div>
  <div class="detail-panel">
    <div class="detail-header">
      <button class="close-btn" onclick={closeDetail}>&times;</button>
    </div>
    <div class="detail-content">
      <div class="detail-image">
        <img src="/api/images/{selectedImage.filename}/file" alt={selectedImage.filename} />
      </div>
      <div class="detail-info">
        <h2>{selectedImage.filename}</h2>
        <div class="detail-meta">
          <p><strong>Status:</strong> <span class={statusClass(selectedImage.status)}>{selectedImage.status}</span></p>
          <p><strong>Media:</strong>
            <select bind:value={selectedImage.media_type} onchange={() => updateField(selectedImage.filename, 'media_type', selectedImage.media_type)} class="detail-select">
              {#each ['photograph', 'illustration', 'manga', 'unknown'] as mt}
                <option value={mt}>{mt}</option>
              {/each}
            </select>
            <select bind:value={selectedImage.style} onchange={() => updateField(selectedImage.filename, 'style', selectedImage.style || null)} class="detail-select">
              <option value="">—</option>
              {#each ['realistic', 'manga', 'color_illustration', 'monochrome', 'colored', 'landscape', 'portrait', 'street', 'still_life', 'animal', 'plants'] as st}
                <option value={st}>{st}</option>
              {/each}
            </select>
          </p>
          <p><strong>NSFW:</strong>
            <select bind:value={selectedImage.nsfw} onchange={() => updateField(selectedImage.filename, 'nsfw', selectedImage.nsfw === 'yes')} class="detail-select">
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </p>
          <p><strong>Author:</strong> {selectedImage.author_username || '-'}</p>
          <p><strong>Posted:</strong> {selectedImage.posted_at || '-'}</p>
        </div>

        {#if selectedImage.palette?.length}
          <div class="palette-bar large" style={paletteStyle(selectedImage.palette)}></div>
        {/if}

        {#if selectedImage.artists?.length}
          <div class="section">
            <h3>Artists</h3>
            <div class="tags-list">
              {#each selectedImage.artists as a}
                <span class="tag artist" title={`${a.confidence}`}>{a.label} ({a.confidence})</span>
              {/each}
            </div>
          </div>
        {/if}

        {#if selectedImage.characters?.length}
          <div class="section">
            <h3>Characters</h3>
            <div class="tags-list">
              {#each selectedImage.characters as c}
                <span class="tag character" title={`${c.confidence}`}>{c.label} ({c.confidence})</span>
              {/each}
            </div>
          </div>
        {/if}

        <div class="section">
          <h3>Tags (JSON)</h3>
          <textarea bind:value={editingTags} rows="8"></textarea>
          <div class="action-bar">
            <button class="btn primary" onclick={saveTags} disabled={saving}>
              {saving ? 'Saving...' : 'Save Tags'}
            </button>
            <button class="btn" onclick={() => handleRescan(selectedImage.filename)}>Rescan</button>
            <button class="btn danger" onclick={() => handleDelete(selectedImage.filename)}>Delete</button>
          </div>
          <div class="tag-picker">
            <input type="text" bind:value={tagFilter} class="tag-picker-search" placeholder="Filter tags..." />
            <div class="tag-picker-list">
              {#each resolvedTagsFilteredNames as tag}
                <button
                  class="tag-pick-btn"
                  class:in-list={currentTags.includes(tag)}
                  onclick={() => currentTags.includes(tag) ? removeTag(tag) : addTag(tag)}
                >{tag}</button>
              {/each}
            </div>
          </div>
        </div>

        {#if selectedImage.error}
          <div class="error-box">
            <strong>Error:</strong> {selectedImage.error}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#if showTagManager}
  <div class="overlay" onclick={() => showTagManager = false} role="presentation"></div>
  <div class="tag-manager">
    <div class="tag-manager-header">
      <h2>Manage Tags</h2>
      <button class="close-btn" onclick={() => showTagManager = false}>&times;</button>
    </div>
    <div class="tag-manager-body">
      <div class="tag-manager-add">
        <input type="text" bind:value={tagManagerNew} placeholder="Tag name" class="tm-input" />
        <input type="text" bind:value={tagManagerDesc} placeholder="Description" class="tm-input" />
        <button class="btn primary" onclick={addTagManagerTag} disabled={!tagManagerNew.trim()}>Add</button>
      </div>
      <input
        type="text"
        bind:value={tagManagerSearch}
        oninput={loadTagManager}
        placeholder="Search tags..."
        class="tm-input tm-search"
      />
      <div class="tag-manager-list">
        {#each tagManagerTags as t}
          <div class="tm-row">
            {#if tagManagerEditing === t.name}
              <input type="text" bind:value={tagManagerEditDesc} class="tm-input tm-edit" />
              <button class="btn primary" onclick={() => saveTagManagerEdit(t.name)}>Save</button>
              <button class="btn" onclick={() => { tagManagerEditing = null }}>Cancel</button>
            {:else}
              <span class="tm-name">{t.name}</span>
              <span class="tm-desc">{t.description}</span>
              <button class="tag-manager-btn" onclick={() => { tagManagerEditing = t.name; tagManagerEditDesc = t.description }}>Edit</button>
              <button class="tag-manager-btn danger" onclick={() => deleteTagManagerTag(t.name)}>Del</button>
            {/if}
          </div>
        {/each}
        {#if tagManagerTags.length === 0}
          <div class="empty">No tags found</div>
        {/if}
      </div>

      <h3 class="synonym-heading">Synonyms</h3>
      <div class="tag-manager-add">
        <input type="text" bind:value={synonymNew} placeholder="Synonym" class="tm-input" />
        <input type="text" bind:value={synonymCanonical} placeholder="Canonical name" class="tm-input" />
        <button class="btn primary" onclick={addSynonym} disabled={!synonymNew.trim() || !synonymCanonical.trim()}>Add</button>
      </div>
      <input
        type="text"
        bind:value={synonymSearch}
        oninput={loadSynonyms}
        placeholder="Search synonyms..."
        class="tm-input tm-search"
      />
      <div class="tag-manager-list">
        {#each tagSynonyms as s}
          <div class="tm-row">
            <span class="tm-synonym">{s.synonym}</span>
            <span class="tm-arrow">→</span>
            <span class="tm-canonical">{s.canonical}</span>
            <button class="tag-manager-btn danger" onclick={() => deleteSynonym(s.synonym)}>Del</button>
          </div>
        {/each}
        {#if tagSynonyms.length === 0}
          <div class="empty">No synonyms found</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  :global(*) {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f0f0f;
    color: #e0e0e0;
    min-height: 100vh;
  }

  main {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 12px;
  }

  h1 { font-size: 24px; color: #fff; }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }

  .header-buttons {
    display: flex;
    gap: 4px;
  }

  .stats { display: flex; gap: 16px; font-size: 13px; }
  .stat { padding: 4px 10px; background: #1a1a1a; border-radius: 6px; }
  .stat.pending { color: #f0ad4e; }
  .stat.done { color: #5cb85c; }
  .stat.error { color: #d9534f; }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }

  .filters { display: flex; gap: 4px; }
  .filter-btn {
    padding: 6px 14px;
    background: #1a1a1a;
    border: 1px solid #333;
    color: #aaa;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
  }
  .filter-btn.active { background: #2a6eff; color: #fff; border-color: #2a6eff; }
  .filter-btn.primary { background: #2a6eff; color: #fff; border-color: #2a6eff; }
  .filter-btn.primary:disabled { opacity: 0.5; cursor: default; }
  .filter-btn:hover { border-color: #555; }

  .filter-select {
    padding: 6px 10px;
    background: #1a1a1a;
    border: 1px solid #333;
    color: #ccc;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
  }
  .filter-select:focus { outline: none; border-color: #2a6eff; }
  .filter-select option { background: #1a1a1a; }

  .color-divider { width: 1px; align-self: stretch; background: #333; margin: 0 4px; }
  .color-input { width: 34px; height: 30px; padding: 0; border: 1px solid #333; border-radius: 6px; background: #1a1a1a; cursor: pointer; }
  .color-input::-webkit-color-swatch-wrapper { padding: 2px; }
  .color-input::-webkit-color-swatch { border: none; border-radius: 4px; }

  .threshold-label { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #888; }
  .threshold-slider { width: 110px; accent-color: #2a6eff; cursor: pointer; }

  .scroll-sentinel { display: flex; justify-content: center; padding: 20px 0; color: #666; font-size: 13px; }

  .search-wrap { position: relative; flex: 1; min-width: 200px; }
  .search-input {
    width: 100%;
    padding: 8px 32px 8px 14px;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 6px;
    color: #e0e0e0;
    font-size: 13px;
  }
  .search-input:focus { outline: none; border-color: #2a6eff; }
  .search-clear {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 4px;
  }
  .search-clear:hover { color: #ccc; }

  .loading, .empty { text-align: center; padding: 60px 0; color: #666; font-size: 16px; }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  .card {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    overflow: hidden;
    cursor: pointer;
    transition: border-color 0.15s, transform 0.15s;
  }
  .card:hover { border-color: #444; transform: translateY(-2px); }
  .card.selected { border-color: #2a6eff; }
  .card.rescan-selected { border-color: #f0ad4e; outline: 2px solid #f0ad4e; }

  .check-overlay {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #f0ad4e;
    color: #000;
    font-size: 14px;
    font-weight: bold;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }

  .card-thumb {
    position: relative;
    aspect-ratio: 1;
    overflow: hidden;
    background: #111;
  }
  .card-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .nsfw-overlay {
    position: absolute;
    top: 6px;
    right: 6px;
    font-size: 18px;
    text-shadow: 0 0 4px #000;
  }

  .card-info { padding: 10px 12px; }
  .card-filename {
    font-size: 12px;
    color: #ccc;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-bottom: 6px;
  }
  .card-meta {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }
  .media-type { font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; }
  .media-type.type-photo { color: #5bc0de; background: #1a2a3a; }
  .media-type.type-illust { color: #b8a0e8; background: #2a1a3a; }
  .media-type.style-tag { color: #c9a0ff; background: #2a1a3a; }

  .badge-done { color: #5cb85c; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .badge-pending { color: #f0ad4e; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .badge-error { color: #d9534f; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .badge-edited { color: #7c6aff; font-size: 10px; font-weight: 600; text-transform: uppercase; background: #1a1a3a; padding: 1px 6px; border-radius: 4px; }
  .badge-nsfw { color: #d9534f; font-size: 10px; font-weight: 600; text-transform: uppercase; background: #3a1a1a; padding: 1px 6px; border-radius: 4px; }

  .card-author {
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 11px;
    color: #777;
    margin-bottom: 6px;
  }
  .card-author span:first-child { color: #888; }
  .card-date { color: #555 !important; }

  .palette-bar {
    height: 6px;
    border-radius: 3px;
    margin-bottom: 6px;
  }
  .palette-bar.large { height: 10px; margin-bottom: 12px; }

  .card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
  .tag {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    background: #2a2a2a;
    color: #aaa;
  }
  .tag.artist { color: #7cb8ff; background: #1a2a4a; font-size: 11px; font-weight: 600; }
  .tag.character { color: #ff9f7c; background: #4a2a1a; font-size: 11px; }
  .tag.content { color: #b8e0a8; background: #1f3a1a; }

  .tags-list { display: flex; flex-wrap: wrap; gap: 6px; }
  .tags-list .tag { font-size: 12px; padding: 3px 8px; }

  /* --- Detail Panel --- */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 100;
  }

  .detail-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 90vw;
    max-width: 900px;
    max-height: 90vh;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 12px;
    z-index: 101;
    overflow: auto;
    display: flex;
    flex-direction: column;
  }

  .detail-header {
    display: flex;
    justify-content: flex-end;
    padding: 8px 8px 0;
    flex-shrink: 0;
  }

  .close-btn {
    width: 32px;
    height: 32px;
    background: #333;
    border: none;
    color: #fff;
    font-size: 20px;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .close-btn:hover { background: #555; }

  .detail-content {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    padding: 0 20px 20px;
    overflow: auto;
  }

  @media (max-width: 768px) {
    .detail-content { grid-template-columns: 1fr; }
  }

  .detail-image img {
    width: 100%;
    border-radius: 8px;
  }

  .detail-info h2 {
    font-size: 16px;
    color: #fff;
    margin-bottom: 12px;
    word-break: break-all;
  }

  .detail-meta p { margin-bottom: 6px; font-size: 13px; color: #aaa; }
  .detail-meta strong { color: #ccc; }
  .detail-select {
    padding: 2px 6px;
    background: #111;
    border: 1px solid #333;
    border-radius: 4px;
    color: #ccc;
    font-size: 12px;
    cursor: pointer;
  }
  .detail-select:focus { outline: none; border-color: #2a6eff; }
  .detail-select option { background: #111; }

  .section { margin-top: 16px; }
  .section h3 { font-size: 13px; color: #888; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }

  textarea {
    width: 100%;
    padding: 8px;
    background: #111;
    border: 1px solid #333;
    border-radius: 6px;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 12px;
    resize: vertical;
  }
  textarea:focus { outline: none; border-color: #2a6eff; }

  .action-bar { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }

  .btn {
    padding: 8px 16px;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    background: #333;
    color: #e0e0e0;
  }
  .btn:hover { background: #444; }
  .btn.primary { background: #2a6eff; color: #fff; }
  .btn.primary:hover { background: #1a5eef; }
  .btn.primary:disabled { opacity: 0.5; }
  .btn.danger { background: #a94442; color: #fff; }
  .btn.danger:hover { background: #c9302c; }

  .error-box {
    margin-top: 12px;
    padding: 10px;
    background: #2a1010;
    border: 1px solid #a94442;
    border-radius: 6px;
    color: #d9534f;
    font-size: 13px;
  }

  .tag-picker {
    margin-top: 10px;
    border-top: 1px solid #333;
    padding-top: 10px;
  }

  .tag-picker-search {
    width: 100%;
    padding: 6px 10px;
    background: #111;
    border: 1px solid #333;
    border-radius: 6px;
    color: #e0e0e0;
    font-size: 12px;
    margin-bottom: 8px;
  }
  .tag-picker-search:focus { outline: none; border-color: #2a6eff; }

  .tag-picker-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    max-height: 160px;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .tag-pick-btn {
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid #333;
    background: #1a1a1a;
    color: #888;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }
  .tag-pick-btn:hover { border-color: #555; color: #ccc; }
  .tag-pick-btn.in-list {
    background: #2a6eff;
    color: #fff;
    border-color: #2a6eff;
  }

  .tag-filter-wrap { position: relative; }
  .tag-filter-input { width: 120px; }
  .tag-filter-clear {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    font-size: 12px;
    padding: 2px 4px;
  }
  .tag-filter-clear:hover { color: #ccc; }
  .tag-filter-no-tag {
    display: inline-flex;
    align-items: center;
    padding: 6px 10px;
    background: #1a1a1a;
    border: 1px solid #2a6eff;
    border-radius: 6px;
    color: #2a6eff;
    font-size: 13px;
    cursor: default;
  }
  .tag-filter-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 6px;
    max-height: 250px;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: none;
    -ms-overflow-style: none;
    z-index: 10;
    margin-top: 2px;
  }
  .tag-filter-option {
    display: block;
    width: 100%;
    text-align: left;
    padding: 6px 10px;
    background: none;
    border: none;
    color: #ccc;
    font-size: 12px;
    cursor: pointer;
  }
  .tag-filter-option:hover { background: #2a2a2a; }

  .tag-filter-dropdown::-webkit-scrollbar { display: none; }

  .tag-manager {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 600px;
    max-width: 90vw;
    max-height: 80vh;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 12px;
    z-index: 101;
    display: flex;
    flex-direction: column;
  }

  .tag-manager-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }
  .tag-manager-header h2 { font-size: 16px; color: #fff; margin: 0; }

  .tag-manager-body {
    padding: 12px 16px;
    overflow-y: auto;
    flex: 1;
  }

  .tag-manager-add {
    display: flex;
    gap: 6px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }

  .tm-input {
    padding: 6px 10px;
    background: #111;
    border: 1px solid #333;
    border-radius: 6px;
    color: #e0e0e0;
    font-size: 12px;
    flex: 1;
    min-width: 120px;
  }
  .tm-input:focus { outline: none; border-color: #2a6eff; }
  .tm-input.tm-search { width: 100%; margin-bottom: 8px; }
  .tm-input.tm-edit { flex: 1; }

  .tag-manager-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .tm-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    background: #111;
    border-radius: 6px;
    font-size: 12px;
  }

  .tm-name {
    color: #e0e0e0;
    font-weight: 600;
    min-width: 120px;
  }
  .tm-desc {
    color: #888;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tag-manager-btn {
    padding: 3px 10px;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #aaa;
    cursor: pointer;
    font-size: 11px;
  }
  .tag-manager-btn:hover { border-color: #666; }

  .synonym-heading {
    color: #fff;
    font-size: 14px;
    margin: 16px 0 8px;
    padding-top: 12px;
    border-top: 1px solid #333;
  }

  .tm-synonym { color: #5cb85c; font-weight: 600; min-width: 120px; }
  .tm-arrow { color: #555; }
  .tm-canonical { color: #e0e0e0; flex: 1; }
  .tag-manager-btn.danger { color: #d9534f; border-color: #5a2222; }
  .tag-manager-btn.danger:hover { background: #3a1515; }
</style>
