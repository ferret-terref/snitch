""" Constants for Stash API interactions """

GRAPHQL_METADATA_SCAN = """
mutation MetadataScan($input: ScanMetadataInput!) {
    metadataScan(input: $input)
}
"""

GRAPHQL_STASH_TASKS_QUERY = """
query JobQueue {
    jobQueue {
        id
        status
        subTasks
        description
        progress
        startTime
        endTime
        addTime
        error
    }
}
"""

GRAPHQL_SCENES_QUERY = """
query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType, $scene_ids: [Int!]) {
    findScenes(filter: $filter, scene_filter: $scene_filter, scene_ids: $scene_ids) {
        count
        filesize
        duration
        scenes {
            ...SlimSceneData
            __typename
        }
        __typename
    }
}

fragment SlimSceneData on Scene {
    id
    title
    code
    details
    director
    urls
    date
    rating100
    o_counter
    organized
    interactive
    interactive_speed
    resume_time
    play_duration
    play_count
    files {
        ...VideoFileData
        __typename
    }
    paths {
        screenshot
        preview
        stream
        webp
        vtt
        sprite
        funscript
        interactive_heatmap
        caption
        __typename
    }
    scene_markers {
        id
        title
        seconds
        primary_tag {
            id
            name
            __typename
        }
        __typename
    }
    galleries {
        id
        files {
            path
            __typename
        }
        folder {
            path
            __typename
        }
        title
        __typename
    }
    studio {
        id
        name
        image_path
        __typename
    }
    groups {
        group {
            id
            name
            front_image_path
            __typename
        }
        scene_index
        __typename
    }
    tags {
        id
        name
        __typename
    }
    performers {
        id
        name
        disambiguation
        gender
        favorite
        image_path
        __typename
    }
    stash_ids {
        endpoint
        stash_id
        updated_at
        __typename
    }
    __typename
}

fragment VideoFileData on VideoFile {
    id
    path
    size
    mod_time
    duration
    video_codec
    audio_codec
    width
    height
    frame_rate
    bit_rate
    fingerprints {
        type
        value
        __typename
    }
    __typename
}
"""

GRAPHQL_IMAGES_QUERY = """
query FindImages($filter: FindFilterType, $image_filter: ImageFilterType, $image_ids: [Int!]) {
    findImages(filter: $filter, image_filter: $image_filter, image_ids: $image_ids) {
        count
        megapixels
        filesize
        images {
            ...SlimImageData
            __typename
        }
        __typename
    }
}

fragment SlimImageData on Image {
    id
    title
    code
    date
    urls
    details
    photographer
    rating100
    organized
    o_counter
    paths {
        thumbnail
        preview
        image
        __typename
    }
    galleries {
        id
        title
        files {
            path
            __typename
        }
        folder {
            path
            __typename
        }
        __typename
    }
    studio {
        id
        name
        image_path
        __typename
    }
    tags {
        id
        name
        __typename
    }
    performers {
        id
        name
        gender
        favorite
        image_path
        __typename
    }
    visual_files {
        ...VisualFileData
        __typename
    }
    __typename
}

fragment VisualFileData on VisualFile {
    ... on BaseFile {
        id
        path
        size
        mod_time
        fingerprints {
            type
            value
            __typename
        }
        __typename
    }
    ... on ImageFile {
        id
        path
        size
        mod_time
        width
        height
        fingerprints {
            type
            value
            __typename
        }
        __typename
    }
    ... on VideoFile {
        id
        path
        size
        mod_time
        duration
        video_codec
        audio_codec
        width
        height
        frame_rate
        bit_rate
        fingerprints {
            type
            value
            __typename
        }
        __typename
    }
    __typename
}
"""

GRAPHQL_GALLERIES_QUERY = """
query FindGalleries($filter: FindFilterType, $gallery_filter: GalleryFilterType) {
    findGalleries(gallery_filter: $gallery_filter, filter: $filter) {
        count
        galleries {
            id
            title
            urls
            folder {
                id
                path
            }
        }
    }
}
"""

GRAPHQL_TAGS_QUERY = """
query FindTags {
    findTags(
        filter: { q: "", page: 1, per_page: 99999999, sort: "name", direction: ASC }
        tag_filter: {}
    ) {
        tags { id name }
    }
}
"""

GRAPHQL_UPDATE_SCENE = """
mutation SceneUpdate($input: SceneUpdateInput!) {
    sceneUpdate(input: $input) {
        id
        tags { id name }
        url
        title
    }
}
"""

GRAPHQL_UPDATE_IMAGE = """
mutation ImageUpdate($input: ImageUpdateInput!) {
    imageUpdate(input: $input) {
        id
        tags { id name }
        url
        title
    }
}
"""

GRAPHQL_UPDATE_GALLERY = """
mutation GalleryUpdate($input: GalleryUpdateInput!) {
    galleryUpdate(input: $input) {
        id
        urls
        title
        tags {
            id
            name
        }
    }
}
"""

GRAPHQL_CREATE_TAG = """
mutation TagCreate($input: TagCreateInput!) {
    tagCreate(input: $input) {
        id
        name
    }
}
"""
