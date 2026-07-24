export const BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/+$/, '');

async function request(path, options = {}) {
	const res = await fetch(`${BASE}${path}`, {
		headers: { "Content-Type": "application/json", ...options.headers },
		...options,
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		throw new Error(err.error || `HTTP ${res.status}`);
	}
	return res.json();
}

export function getImages(filters = {}, page = 1, perPage = 24) {
	const params = new URLSearchParams();
	for (const [k, v] of Object.entries(filters)) {
		if (v) params.append(k, v);
	}
	params.set("page", String(page));
	params.set("per_page", String(perPage));
	const qs = params.toString();
	return request(`/images${qs ? `?${qs}` : ""}`);
}

export function getFilters(filters = {}) {
	const params = new URLSearchParams();
	for (const [k, v] of Object.entries(filters)) {
		if (v) params.append(k, v);
	}
	const qs = params.toString();
	return request(`/filters${qs ? `?${qs}` : ""}`);
}

export function getImagesByColor(
	r,
	g,
	b,
	threshold = 100,
	page = 1,
	perPage = 24,
) {
	const params = new URLSearchParams();
	params.set("r", String(r));
	params.set("g", String(g));
	params.set("b", String(b));
	params.set("threshold", String(threshold));
	params.set("page", String(page));
	params.set("per_page", String(perPage));
	return request(`/images/color?${params.toString()}`);
}
export function getImage(filename) {
	return request(`/images/${encodeURIComponent(filename)}`);
}

export function updateImage(filename, data) {
	return request(`/images/${encodeURIComponent(filename)}`, {
		method: "PUT",
		body: JSON.stringify(data),
	});
}

export function deleteImage(filename) {
	return request(`/images/${encodeURIComponent(filename)}`, {
		method: "DELETE",
	});
}

export function getStats() {
	return request("/stats");
}

export function getTagsMeta(search) {
	const params = search ? `?search=${encodeURIComponent(search)}` : "";
	return request(`/tags-meta${params}`);
}

export function addTagMeta(name, description) {
	return request("/tags-meta", {
		method: "POST",
		body: JSON.stringify({ name, description }),
	});
}

export function updateTagMeta(name, description) {
	return request(`/tags-meta/${encodeURIComponent(name)}`, {
		method: "PUT",
		body: JSON.stringify({ description }),
	});
}

export function deleteTagMeta(name) {
	return request(`/tags-meta/${encodeURIComponent(name)}`, {
		method: "DELETE",
	});
}

export function getTagSynonyms(search) {
	const params = search ? `?search=${encodeURIComponent(search)}` : "";
	return request(`/tag-synonyms${params}`);
}

export function addTagSynonym(synonym, canonical) {
	return request("/tag-synonyms", {
		method: "POST",
		body: JSON.stringify({ synonym, canonical }),
	});
}

export function deleteTagSynonym(synonym) {
	return request(`/tag-synonyms/${encodeURIComponent(synonym)}`, {
		method: "DELETE",
	});
}

export function setImagesPending(filters = {}) {
	return request("/images/set-pending", {
		method: "PUT",
		body: JSON.stringify(filters),
	});
}

export function getHistogram(filename, bins = 32) {
	return request(`/images/${encodeURIComponent(filename)}/histogram?bins=${bins}`);
}
