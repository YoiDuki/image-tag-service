<script>
  import { onMount } from 'svelte'
  import { getImages, getImagesByColor, getStats, getFilters, updateImage, deleteImage, getTagsMeta, addTagMeta, updateTagMeta, deleteTagMeta, getTagSynonyms, addTagSynonym, deleteTagSynonym, setImagesPending } from './lib/api.js'

  const _CLIP_LABELS = [
    { idx: 0, label: 'Photograph', isMedia: true, isMatch: (img) => img.media_type === 'photograph' },
    { idx: 1, label: 'Illustration', isMedia: true, isMatch: (img) => img.media_type === 'illustration' },
    { idx: 2, label: 'Manga', isMedia: true, isMatch: (img) => img.media_type === 'manga' },
    { idx: 3, label: 'Tutorial', isMedia: true, isMatch: (img) => img.media_type === 'tutorial' },
    { idx: 4, label: 'Portrait', isMatch: (img) => img.style === 'portrait' },
    { idx: 5, label: 'Street', isMatch: (img) => img.style === 'street' },
    { idx: 6, label: 'Landscape', isMatch: (img) => img.style === 'landscape' },
    { idx: 7, label: 'Still Life', isMatch: (img) => img.style === 'still_life' },
    { idx: 8, label: 'Animal', isMatch: (img) => img.style === 'animal' },
    { idx: 9, label: 'Plants', isMatch: (img) => img.style === 'plants' },
    { idx: 10, label: 'Anime', isMatch: (img) => img.style === 'anime' },
    { idx: 11, label: 'Realistic', isMatch: (img) => img.style === 'realistic' },
    { idx: 12, label: 'Rakugaki', isMatch: (img) => img.style === 'rakugaki' },
    { idx: 13, label: 'Scenery', isMatch: (img) => img.style === 'scenery' },
    { idx: 14, label: 'Colored Manga', isMatch: (img) => img.style === 'colored' },
    { idx: 15, label: 'Monochrome Manga', isMatch: (img) => img.style === 'monochrome' },
  ]

  let images = $state([])
  let stats = $state({ total: 0, pending: 0, done: 0, error: 0 })
  let filterOptions = $state({ authors: [], media_types: [], styles: [], tags: [] })
  let filters = $state({
    author: '',
    media_type: '',
    style: '',
    tags: [],
    nsfw: '',
    search: '',
    sort: 'updated_at',
  })
  let colorPick = $state('#888888')
  let colorThreshold = $state(30)
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
  let loadedImgs = $state(new Set())
  let showTagManager = $state(false)
  let tagManagerTags = $state([])
  let tagManagerSearch = $state('')
  let tagManagerNew = $state('')
  let tagManagerDesc = $state('')
  let tagManagerEditing = $state(null)
  let tagManagerEditDesc = $state('')
  let tagFilterText = $state('')
  let tagFilterFocused = $state(false)
  let authorFilterFocused = $state(false)
  let authorInputEl = $state(null)
  let tagFilterInputEl = $state(null)
  let authorDropdownStyle = $state('')
  let tagDropdownStyle = $state('')

  function positionAuthorDropdown() {
    authorFilterFocused = true
    updateAuthorDropdownPos()
  }

  function updateAuthorDropdownPos() {
    if (!authorInputEl || !authorFilterFocused) return
    const r = authorInputEl.getBoundingClientRect()
    const maxH = Math.min(240, window.innerHeight - r.bottom - 16)
    authorDropdownStyle = `top:${r.bottom + 4}px;left:${r.left}px;min-width:${Math.max(128, r.width)}px;max-height:${maxH}px;`
  }

  function positionTagDropdown() {
    tagFilterFocused = true
    updateTagDropdownPos()
  }

  function updateTagDropdownPos() {
    if (!tagFilterInputEl || !tagFilterFocused) return
    const r = tagFilterInputEl.getBoundingClientRect()
    const maxH = Math.min(240, window.innerHeight - r.bottom - 16)
    tagDropdownStyle = `top:${r.bottom + 4}px;left:${r.left}px;min-width:${Math.max(128, r.width)}px;max-height:${maxH}px;`
  }

  $effect(() => {
    if (authorFilterFocused) {
      const handler = () => updateAuthorDropdownPos()
      window.addEventListener('scroll', handler, { passive: true })
      return () => window.removeEventListener('scroll', handler)
    }
  })

  $effect(() => {
    if (tagFilterFocused) {
      const handler = () => updateTagDropdownPos()
      window.addEventListener('scroll', handler, { passive: true })
      return () => window.removeEventListener('scroll', handler)
    }
  })

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
      const raw = filterOptions.tags
      for (const t of raw) {
        const tagName = typeof t === 'string' ? t : t.name
        const count = typeof t === 'string' ? 0 : (t.count || 0)
        const canonical = synonymMap[tagName] || tagName
        if (!map[canonical]) map[canonical] = { name: canonical, count: 0 }
        map[canonical].count += count || 1
      }
      return Object.values(map).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    })()
  )

  const resolvedTagNames = $derived(resolvedTagsAll.map(t => t.name))

  const rawTagNames = $derived(
    (filterOptions.raw_tags || filterOptions.tags).map(t => typeof t === 'string' ? t : t.name)
  )

  const rawTagNamesFiltered = $derived(
    tagFilter ? rawTagNames.filter(n => n.toLowerCase().includes(tagFilter.toLowerCase())) : rawTagNames
  )

  const rawTagCounts = $derived(
    (filterOptions.raw_tags || filterOptions.tags).map(t => ({ name: typeof t === 'string' ? t : t.name, count: typeof t === 'string' ? 0 : (t.count || 0) }))
  )

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
        const apiFilters = {}
        for (const [k, v] of Object.entries(filters)) {
          if (k === 'tags') {
            if (v.length) apiFilters.tag = v.join(',')
          } else if (v) {
            apiFilters[k] = v
          }
        }
        res = await getImages({ ...apiFilters, search }, 1)
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
        const apiFilters = {}
        for (const [k, v] of Object.entries(filters)) {
          if (k === 'tags') {
            if (v.length) apiFilters.tag = v.join(',')
          } else if (v) {
            apiFilters[k] = v
          }
        }
        res = await getImages({ ...apiFilters, search }, next)
      }
      images = [...images, ...res.images]
      pageInfo = res
      page = next
      allLoaded = next >= res.total_pages
    } catch (e) {
      console.error('Failed to load more:', e)
    } finally {
      loadingMore = false
      // If sentinel still visible after load, keep loading
      if (!allLoaded && sentinelEl) {
        const rect = sentinelEl.getBoundingClientRect()
        if (rect.top < window.innerHeight + 400) {
          loadMore()
        }
      }
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
      filterOptions = await getFilters({
        author: filters.author || undefined,
        media_type: filters.media_type || undefined,
        style: filters.style || undefined,
        tag: filters.tags.length ? filters.tags.join(',') : undefined,
        nsfw: filters.nsfw || undefined,
        search: search || undefined,
      })
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
      loadFilterOptions()
    }, 300)
  }

  function clearSearch() {
    search = ''
    if (searchTimer) clearTimeout(searchTimer)
    page = 1
    loadImages()
    loadFilterOptions()
  }

  function applyFilters() {
    colorActive = false
    page = 1
    loadImages()
    loadFilterOptions()
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
    filters = { author: '', media_type: '', style: '', tags: [], nsfw: '', sort: 'updated_at' }
    if (searchTimer) clearTimeout(searchTimer)
    search = ''
    colorActive = false
    page = 1
    loadImages()
  }

  function addTagFilter(t) {
    if (!filters.tags.includes(t)) {
      filters.tags = [...filters.tags, t]
      applyFilters()
    }
  }

  function removeTagFilter(t) {
    filters.tags = filters.tags.filter(x => x !== t)
    applyFilters()
  }

  function filterByTag(t) {
    addTagFilter(t)
  }

  function filterByColor(hex) {
    filters.tags = []
    colorPick = hex
    colorActive = true
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

  async function selectAllFiltered() {
    const activeFilters = {
      author: filters.author || undefined,
      media_type: filters.media_type || undefined,
      style: filters.style || undefined,
      tag: filters.tags.length ? filters.tags.join(',') : undefined,
      nsfw: filters.nsfw || undefined,
      search: search || undefined,
    }
    const res = await setImagesPending(activeFilters)
    rescanMode = false
    selectedForRescan = new Set()
    await loadImages()
    await loadStats()
    alert(`Set ${res.affected} image(s) to pending. Run 'python run_tag.py process' to process.`)
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

<main class="max-w-[1400px] mx-auto p-5 overflow-x-hidden">
  <div class="navbar mb-5 gap-4 flex-wrap">
    <div class="flex-1">
      <h1 class="text-2xl font-bold text-base-content">Image Tag Service</h1>
    </div>
    <div class="flex items-center gap-4 flex-wrap">
      <div class="flex gap-4 text-sm">
        {#if pageInfo.total > 0}<span class="badge badge-ghost badge-sm text-primary">Filtered: {pageInfo.total}</span>{/if}
        <span class="badge badge-ghost badge-sm">Total: {stats.total}</span>
        <span class="badge badge-ghost badge-sm text-warning">Pending: {stats.pending}</span>
        <span class="badge badge-ghost badge-sm text-success">Done: {stats.done}</span>
        <span class="badge badge-ghost badge-sm text-error">Error: {stats.error}</span>
      </div>
      <div class="flex gap-1">
        <button class="btn btn-sm btn-neutral" class:btn-primary={rescanMode} onclick={toggleRescanMode}>
          {rescanMode ? 'Cancel' : 'Rescan'}
        </button>
        {#if rescanMode}
          <button class="btn btn-sm btn-primary" onclick={selectAllFiltered}>Select All ({pageInfo.total})</button>
          <button class="btn btn-sm btn-primary" onclick={startRescan} disabled={rescanning || selectedForRescan.size === 0}>
            {rescanning ? 'Processing...' : `Start (${selectedForRescan.size})`}
          </button>
        {/if}
        <button class="btn btn-sm btn-neutral" onclick={() => { showTagManager = true; tagManagerSearch = ''; synonymSearch = ''; loadTagManager(); loadSynonyms() }}>Manage Tags</button>
      </div>
    </div>
  </div>

  <div class="flex gap-1 mb-5 px-[5px] pb-[5px] pt-[7px] flex-wrap items-center">
      <div class="inline-block relative">
        <input
          type="text"
          bind:value={filters.author}
          bind:this={authorInputEl}
          onfocus={positionAuthorDropdown}
          onblur={() => setTimeout(() => authorFilterFocused = false, 150)}
          oninput={applyFilters}
          placeholder="Author: All"
          class="input input-bordered input-sm w-32"
        />
        {#if filters.author}
          <button class="absolute right-1 top-1/2 -translate-y-1/2 btn btn-neutral btn-xs px-1 min-h-0 h-auto text-base-content/40" onclick={() => { filters.author = ''; applyFilters() }}>✕</button>
        {/if}
      </div>
      {#if authorFilterFocused && filteredAuthorOptions.length > 0}
        <div style={authorDropdownStyle} class="fixed z-[99999] flex flex-col p-2 shadow bg-base-200 rounded-box overflow-y-auto overflow-x-hidden dropdown-scroll">
          {#each filteredAuthorOptions.slice(0, 50) as a}
            <button class="block w-full text-left px-2.5 py-1.5 text-xs text-base-content hover:bg-base-300 cursor-pointer bg-none border-none" onmousedown={() => { filters.author = a.name; applyFilters(); authorFilterFocused = false; document.activeElement?.blur() }}>{a.name} ({a.count})</button>
          {/each}
        </div>
      {/if}

      <select bind:value={filters.nsfw} onchange={(e) => { applyFilters(); e.target.blur() }} class="select select-bordered select-sm w-28">
        <option value="">NSFW: All</option>
        <option value="no">No NSFW</option>
        <option value="yes">NSFW only</option>
      </select>
      <select bind:value={filters.media_type} onchange={(e) => { applyFilters(); e.target.blur() }} class="select select-bordered select-sm w-28">
        <option value="">Media: All</option>
        {#each filterOptions.media_types as m}
          <option value={m.name}>{m.name} ({m.count})</option>
        {/each}
      </select>
      <select bind:value={filters.style} onchange={(e) => { applyFilters(); e.target.blur() }} class="select select-bordered select-sm w-28">
        <option value="">Style: All</option>
        {#each filterOptions.styles as s}
          <option value={s.name}>{s.name} ({s.count})</option>
        {/each}
      </select>

      <div class="inline-block relative">
        <input
          type="text"
          bind:value={tagFilterText}
          bind:this={tagFilterInputEl}
          onfocus={positionTagDropdown}
          onblur={() => setTimeout(() => tagFilterFocused = false, 200)}
          oninput={positionTagDropdown}
          placeholder="Tag: Search / Click card to filter"
          class="input input-bordered input-sm w-32"
        />
      </div>
      {#if tagFilterFocused}
        <div style={tagDropdownStyle} class="fixed z-[99999] flex flex-col p-2 shadow bg-base-200 rounded-box overflow-y-auto overflow-x-hidden dropdown-scroll">
          {#each rawTagCounts.filter(t => !tagFilterText || t.name.toLowerCase().includes(tagFilterText.toLowerCase())).slice(0, 50) as t}
            <button class="block w-full text-left px-2.5 py-1.5 text-xs text-base-content hover:bg-base-300 cursor-pointer bg-none border-none" onmousedown={(e) => { e.preventDefault(); addTagFilter(t.name); tagFilterFocused = false; tagFilterText = ''; document.activeElement?.blur() }}>{t.name} ({t.count})</button>
          {/each}
        </div>
      {/if}

      <select bind:value={filters.sort} onchange={(e) => { applyFilters(); e.target.blur() }} class="select select-bordered select-sm w-32">
        <option value="updated_at">Sort: Updated</option>
        <option value="posted_at">Sort: Posted</option>
      </select>

      <div class="w-px self-stretch bg-base-300 mx-1"></div>

      <input
        type="color"
        value={colorPick}
        onchange={applyColor}
        class="input input-bordered w-8 h-8 p-1 rounded-full"
        title="Filter by palette color"
      />

      {#if colorActive}
        <label class="flex items-center gap-1.5 text-xs text-base-content/50">
          <span>Δ {colorThreshold}</span>
          <input
            type="range"
            min="0"
            max="441"
            bind:value={colorThreshold}
            onchange={applyThreshold}
            class="range range-sm w-28"
          />
        </label>
        <button class="btn btn-neutral btn-sm" onclick={clearColor} title="Clear color filter">✕</button>
      {/if}
      <button class="btn btn-neutral btn-sm" onclick={resetFilters}>Reset</button>

      <label class="input input-bordered input-sm flex items-center gap-2 flex-1 min-w-48 ml-1">
        <input
          type="text"
          placeholder="Search filename, author, character, style, media..."
          bind:value={search}
          oninput={onSearchInput}
          class="grow"
        />
        {#if search}
          <button class="btn btn-neutral btn-xs" onclick={clearSearch}>✕</button>
        {/if}
      </label>
  </div>

  {#if filters.tags.length}
    <div class="overflow-y-auto max-h-[25vh] mb-3">
    <div class="flex flex-wrap gap-1.5 px-1">
      {#each filters.tags as t}
        <span class="badge badge-primary badge-lg gap-1">
          {synonymMap[t] || t}
          <button class="btn btn-neutral btn-xs text-inherit p-0 min-h-0 h-auto" onclick={() => removeTagFilter(t)}>✕</button>
        </span>
      {/each}
    </div>
  </div>
  {/if}

  {#if loading}
    <div class="flex justify-center py-16 text-base-content/40 text-base">Loading...</div>
  {:else if images.length === 0}
    <div class="flex justify-center py-16 text-base-content/40 text-base">No images found</div>
  {:else}
    <div class="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
      {#each images as img (img.filename)}
        <div
          class="card card-compact bg-base-200 cursor-pointer transition-shadow duration-200 hover:shadow-xl border border-base-300"
          class:border-primary={selectedImage?.filename === img.filename}
          class:border-warning={selectedForRescan.has(img.filename)}
          onclick={() => { if (rescanMode) { toggleSelect(img.filename) } else { openDetail(img) } }}
          role="button"
          tabindex="0"
          onkeydown={(e) => e.key === 'Enter' && (rescanMode ? toggleSelect(img.filename) : openDetail(img))}
        >
          <figure class="relative aspect-square overflow-hidden bg-base-300">
            {#if !loadedImgs.has(img.filename)}
              <div class="absolute inset-0 bg-base-300 animate-pulse"></div>
            {/if}
            <img
              src="/api/images/{img.filename}/file"
              alt={img.filename}
              loading="lazy"
              onload={() => loadedImgs = new Set([...loadedImgs, img.filename])}
              class="w-full h-full object-cover"
              class:opacity-0={!loadedImgs.has(img.filename)}
            />
            <span class="absolute top-1.5 right-1.5 text-lg drop-shadow-[0_0_4px_rgba(0,0,0,1)]">{nsfwBadge(img.nsfw)}</span>
            {#if rescanMode}
              <span class="absolute top-1.5 left-1.5 w-6 h-6 rounded-full bg-warning flex items-center justify-center text-black text-sm font-bold leading-none">{selectedForRescan.has(img.filename) ? '✓' : ''}</span>
            {/if}
          </figure>
          <div class="card-body p-3 gap-1">
            {#if img.author_username || img.posted_at}
              <div class="flex gap-2 items-center text-xs text-base-content/40 mb-1">
                {#if img.author_username}<span class="text-base-content/50">@{img.author_username}</span>{/if}
                {#if img.posted_at}<span class="text-base-content/30">{formatDate(img.posted_at)}</span>{/if}
              </div>
            {/if}
            <div class="flex gap-1.5 items-center mb-1.5">
              {#if img.tags_edited === '1' || img.tags_edited === 1}
                <span class="badge badge-xs badge-ghost">edited</span>
              {/if}
              {#if nsfwBadge(img.nsfw)}<span class="badge badge-xs badge-error">NSFW</span>{/if}
              <span class="badge badge-xs"
                class:badge-info={img.media_type === 'photograph'}
                class:badge-secondary={img.media_type === 'illustration'}
                class:badge-warning={img.media_type === 'manga'}
                class:badge-success={img.media_type === 'tutorial'}
              >{img.media_type}</span>
              {#if img.style}<span class="badge badge-xs badge-ghost">{img.style}</span>{/if}
            </div>
            {#if img.palette?.length}
              <div class="flex gap-0.5 h-1.5 mb-1">
                {#each img.palette as c}
                  <span
                    class="palette-swatch"
                    role="button"
                    tabindex="0"
                    style="background:{c.hex}"
                    title="{c.hex} (click to filter)"
                    onclick={(e) => { e.stopPropagation(); filterByColor(c.hex) }}
                    onkeydown={(e) => e.key === 'Enter' && filterByColor(c.hex)}
                  ></span>
                {/each}
              </div>
            {/if}
            {#if img.tags?.length}
              <div class="flex flex-wrap gap-1">
                {#each [...new Set(img.tags.filter(t => !/_(hair|eyes|skin)$/i.test(typeof t === 'string' ? t : t.label)).slice(0, 4).map(t => ({ eng: typeof t === 'string' ? t : t.label, cn: img.displayed_tags?.[img.tags.indexOf(t)] || resolveTag(typeof t === 'string' ? t : t.label) })))] as { eng, cn }}
                  <span class="badge badge-ghost badge-xs cursor-pointer hover:bg-base-300" role="button" tabindex="0" onclick={(e) => { e.stopPropagation(); filterByTag(eng) }} onkeydown={(e) => e.key === 'Enter' && filterByTag(eng)}>{cn}</span>
                {/each}
              </div>
            {/if}
            {#if img.characters?.length}
              <div class="flex flex-wrap gap-1">
                {#each img.characters.slice(0, 3) as c}
                  <span class="badge badge-ghost badge-xs text-warning">{c.label}</span>
                {/each}
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
    {#if !allLoaded}
      <div bind:this={sentinelEl} class="flex justify-center py-5 text-sm text-base-content/40">
        {#if loadingMore}<span>Loading more…</span>{/if}
      </div>
    {/if}
  {/if}
</main>

{#if selectedImage}
  <dialog class="modal modal-open">
    <div class="modal-box max-w-4xl w-[90vw] max-h-[90vh] flex flex-col">
      <form method="dialog">
        <button class="btn btn-sm btn-circle btn-neutral absolute right-4 top-4" onclick={closeDetail}>✕</button>
      </form>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5 overflow-auto">
        <div>
          <img src="/api/images/{selectedImage.filename}/file" alt={selectedImage.filename} class="w-full rounded-lg" />
        </div>
        <div>
          <h2 class="text-base text-base-content font-bold mb-3 break-all">{selectedImage.filename}</h2>
          <div class="text-sm space-y-1.5">
            <p class="text-base-content/60"><strong class="text-base-content/80">Status:</strong> <span class="badge badge-sm" class:badge-success={selectedImage.status === 'done'} class:badge-error={selectedImage.status === 'error'} class:badge-warning={selectedImage.status === 'pending'}>{selectedImage.status}</span></p>
            <p class="text-base-content/60 flex items-center gap-1.5 flex-wrap"><strong class="text-base-content/80">Media:</strong>
              <select bind:value={selectedImage.media_type} onchange={() => updateField(selectedImage.filename, 'media_type', selectedImage.media_type)} class="select select-bordered select-xs w-auto">
                <option value="">—</option>
                {#each ['photograph', 'illustration', 'manga', 'tutorial', 'unknown'] as mt}
                  <option value={mt}>{mt}</option>
                {/each}
              </select>
              <select bind:value={selectedImage.style} onchange={() => updateField(selectedImage.filename, 'style', selectedImage.style)} class="select select-bordered select-xs w-auto">
                <option value="">—</option>
                {#each ['portrait', 'street', 'landscape', 'still_life', 'animal', 'plants', 'anime', 'realistic', 'rakugaki', 'scenery', 'colored', 'monochrome'] as st}
                  <option value={st}>{st}</option>
                {/each}
              </select>
            </p>
            <p class="text-base-content/60 flex items-center gap-1.5"><strong class="text-base-content/80">NSFW:</strong>
              <select bind:value={selectedImage.nsfw} onchange={() => updateField(selectedImage.filename, 'nsfw', selectedImage.nsfw === 'yes')} class="select select-bordered select-xs w-auto">
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </select>
            </p>
            <p class="text-base-content/60">
              <strong class="text-base-content/80">Author:</strong>
              {#if selectedImage.author_username}
                <a href="https://x.com/{selectedImage.author_username}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-base-content/70 hover:text-base-content no-underline transition-colors">
                  @{selectedImage.author_username}
                  <svg class="w-3.5 h-3.5 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
              {:else}
                -
              {/if}
            </p>
            <p class="text-base-content/60"><strong class="text-base-content/80">Posted:</strong> {selectedImage.posted_at || '-'}</p>
          </div>

          {#if selectedImage.palette?.length}
            <div class="flex gap-0.5 h-2.5 mb-3 palette-bar large">
              {#each selectedImage.palette as c}
                <span class="palette-swatch" style="background:{c.hex}" title="{c.hex}"></span>
              {/each}
            </div>
          {/if}

          {#if selectedImage.clip_scores?.length}
            <div class="mt-4">
              <h3 class="text-xs text-base-content/50 uppercase tracking-wide mb-2">CLIP Scores</h3>
              <div class="flex flex-wrap gap-1">
                {#each _CLIP_LABELS as item}
                  {#if selectedImage.clip_scores[item.idx] > 0.01}
                    <span class="badge badge-xs" class:badge-primary={item.isMedia || item.isMatch(selectedImage)}>
                      {item.label}: {(selectedImage.clip_scores[item.idx] * 100).toFixed(1)}%
                    </span>
                  {/if}
                {/each}
              </div>
            </div>
          {/if}

          {#if selectedImage.artists?.length}
            <div class="mt-4">
              <h3 class="text-xs text-base-content/50 uppercase tracking-wide mb-2">Artists</h3>
              <div class="flex flex-wrap gap-1">
                {#each selectedImage.artists as a}
                  <span class="badge badge-ghost badge-sm text-info" title={`${a.confidence}`}>{a.label} ({a.confidence})</span>
                {/each}
              </div>
            </div>
          {/if}

          {#if selectedImage.characters?.length}
            <div class="mt-4">
              <h3 class="text-xs text-base-content/50 uppercase tracking-wide mb-2">Characters</h3>
              <div class="flex flex-wrap gap-1">
                {#each selectedImage.characters as c}
                  <span class="badge badge-ghost badge-sm text-warning" title={`${c.confidence}`}>{c.label} ({c.confidence})</span>
                {/each}
              </div>
            </div>
          {/if}

          <div class="mt-4">
            <h3 class="text-xs text-base-content/50 uppercase tracking-wide mb-2">Tags (JSON)</h3>
            <textarea bind:value={editingTags} rows="8" class="textarea textarea-bordered font-mono text-xs w-full"></textarea>
            <div class="flex gap-2 mt-2.5 flex-wrap">
              <button class="btn btn-primary btn-sm" onclick={saveTags} disabled={saving}>
                {saving ? 'Saving...' : 'Save Tags'}
              </button>
              <button class="btn btn-neutral btn-sm" onclick={() => handleRescan(selectedImage.filename)}>Rescan</button>
              <button class="btn btn-error btn-sm" onclick={() => handleDelete(selectedImage.filename)}>Delete</button>
            </div>
            <div class="mt-2.5 border-t border-base-300 pt-2.5">
              <input type="text" bind:value={tagFilter} class="input input-bordered w-full text-xs mb-2" placeholder="Filter tags..." />
              <div class="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
                {#each rawTagNamesFiltered as tag}
                  <button
                    class="btn btn-neutral btn-xs"
                    class:btn-primary={currentTags.includes(tag)}
                    onclick={() => currentTags.includes(tag) ? removeTag(tag) : addTag(tag)}
                  >{tag}</button>
                {/each}
              </div>
            </div>
          </div>

          {#if selectedImage.error}
            <div class="mt-3 p-2.5 bg-error/10 border border-error/30 rounded-box text-error text-sm">
              <strong>Error:</strong> {selectedImage.error}
            </div>
          {/if}
        </div>
      </div>
    </div>
  </dialog>
{/if}

{#if showTagManager}
  <dialog class="modal modal-open">
    <div class="modal-box max-w-xl">
      <form method="dialog">
        <button class="btn btn-sm btn-circle btn-neutral absolute right-4 top-4" onclick={() => showTagManager = false}>✕</button>
      </form>
      <h2 class="text-base font-bold mb-4">Manage Tags</h2>
      <div class="space-y-3">
        <details class="collapse collapse-arrow border border-base-300 rounded-box" open>
          <summary class="collapse-title text-sm font-semibold min-h-0 py-2">Tag Descriptions</summary>
          <div class="collapse-content">
            <div class="flex gap-1.5 mb-2.5 flex-wrap pt-1">
              <input type="text" bind:value={tagManagerNew} placeholder="Tag name" class="input input-bordered input-sm flex-1 min-w-28" />
              <input type="text" bind:value={tagManagerDesc} placeholder="Description" class="input input-bordered input-sm flex-1 min-w-28" />
              <button class="btn btn-primary btn-sm" onclick={addTagManagerTag} disabled={!tagManagerNew.trim()}>Add</button>
            </div>
            <input type="text" bind:value={tagManagerSearch} oninput={loadTagManager} placeholder="Search tags..." class="input input-bordered input-sm w-full mb-2" />
            <div class="flex flex-col gap-1 max-h-60 overflow-y-auto">
              {#each tagManagerTags as t}
                <div class="flex items-center gap-1.5 p-2 bg-base-300 rounded-box text-xs">
                  {#if tagManagerEditing === t.name}
                    <input type="text" bind:value={tagManagerEditDesc} class="input input-bordered input-sm flex-1" />
                    <button class="btn btn-primary btn-xs" onclick={() => saveTagManagerEdit(t.name)}>Save</button>
                    <button class="btn btn-neutral btn-xs" onclick={() => { tagManagerEditing = null }}>Cancel</button>
                  {:else}
                    <span class="text-base-content font-semibold min-w-[120px]">{t.name}</span>
                    <span class="text-base-content/50 flex-1 truncate">{t.description}</span>
                    <button class="btn btn-neutral btn-xs" onclick={() => { tagManagerEditing = t.name; tagManagerEditDesc = t.description }}>Edit</button>
                    <button class="btn btn-neutral btn-xs text-error" onclick={() => deleteTagManagerTag(t.name)}>Del</button>
                  {/if}
                </div>
              {/each}
              {#if tagManagerTags.length === 0}
                <div class="text-center py-8 text-base-content/40">No tags found</div>
              {/if}
            </div>
          </div>
        </details>

        <details class="collapse collapse-arrow border border-base-300 rounded-box" open>
          <summary class="collapse-title text-sm font-semibold min-h-0 py-2">Synonyms</summary>
          <div class="collapse-content">
            <div class="flex gap-1.5 mb-2.5 flex-wrap pt-1">
              <input type="text" bind:value={synonymNew} placeholder="Synonym" class="input input-bordered input-sm flex-1 min-w-28" />
              <input type="text" bind:value={synonymCanonical} placeholder="Canonical name" class="input input-bordered input-sm flex-1 min-w-28" />
              <button class="btn btn-primary btn-sm" onclick={addSynonym} disabled={!synonymNew.trim() || !synonymCanonical.trim()}>Add</button>
            </div>
            <input type="text" bind:value={synonymSearch} oninput={loadSynonyms} placeholder="Search synonyms..." class="input input-bordered input-sm w-full mb-2" />
            <div class="flex flex-col gap-1 max-h-60 overflow-y-auto">
              {#each tagSynonyms as s}
                <div class="flex items-center gap-1.5 p-2 bg-base-300 rounded-box text-xs">
                  <span class="text-success font-semibold min-w-[120px]">{s.synonym}</span>
                  <span class="text-base-content/40">→</span>
                  <span class="text-base-content flex-1">{s.canonical}</span>
                  <button class="btn btn-neutral btn-xs text-error" onclick={() => deleteSynonym(s.synonym)}>Del</button>
                </div>
              {/each}
              {#if tagSynonyms.length === 0}
                <div class="text-center py-8 text-base-content/40">No synonyms found</div>
              {/if}
            </div>
          </div>
        </details>
      </div>
    </div>
  </dialog>
{/if}

<style>
  .palette-swatch { flex: 1; border-radius: 2px; cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; }
  .palette-swatch:hover { transform: scaleY(2); box-shadow: 0 0 6px rgba(255,255,255,0.4); z-index: 1; }
  .palette-bar.large .palette-swatch:hover { transform: scaleY(1.5); }
  .dropdown-scroll::-webkit-scrollbar { display: none; }
  .dropdown-scroll { -ms-overflow-style: none; scrollbar-width: none; }
  .btn-neutral { box-shadow: none !important; }
</style>
