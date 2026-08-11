-- This filter processes the whole document at once
function Pandoc(doc)
  -- 1. Find the placeholder ::: {#toc} :::
  local toc_placeholder_index = nil
  for i, block in ipairs(doc.blocks) do
    if block.t == 'Div' and block.identifier == 'toc' then
      toc_placeholder_index = i
      break
    end
  end

  -- 2. If placeholder exists, generate and insert the TOC
  if toc_placeholder_index then
    -- Remove the placeholder div first
    table.remove(doc.blocks, toc_placeholder_index)

    local toc
    if pandoc.structure and pandoc.structure.table_of_contents then
      -- Static TOC with real hyperlink entries — renders in every viewer
      toc = pandoc.structure.table_of_contents(doc)
    else
      toc = pandoc.RawBlock('openxml',
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>' ..
        '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>' ..
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' ..
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    end

    -- Insert the Header and then the TOC at the placeholder's position
    table.insert(doc.blocks, toc_placeholder_index, pandoc.Header(1, "Table of Contents", {class="unlisted"}))
    table.insert(doc.blocks, toc_placeholder_index + 1, toc)
  end

  return doc
end
